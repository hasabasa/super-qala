"""Заявки в управляющую организацию.

Срок выполнения рассчитывается при создании из норматива категории.
Просроченные заявки — главный отчёт в кабинете организации и лучший
аргумент при продаже подписки.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Sequence,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin
from app.shared.enums import RequestPlace, RequestPriority, RequestStatus


class RequestCategory(Base, TimestampMixin):
    __tablename__ = "request_categories"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_request_category_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    sla_hours: Mapped[int] = mapped_column(
        Integer, default=48, nullable=False, comment="Норматив выполнения в часах"
    )
    order_num: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


# Первичный ключ — UUID, поэтому сквозной номер заявки требует
# отдельной последовательности: автоинкремент на неключевой колонке
# PostgreSQL сам не создаёт.
request_number_seq = Sequence("service_request_number_seq", start=1)


class ServiceRequest(Base, TimestampMixin):
    __tablename__ = "service_requests"
    __table_args__ = (
        Index("ix_service_requests_org_status", "organization_id", "status"),
        Index("ix_service_requests_author", "author_id"),
        Index("ix_service_requests_sla", "sla_due_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    number: Mapped[int] = mapped_column(
        Integer,
        request_number_seq,
        server_default=request_number_seq.next_value(),
        unique=True,
        nullable=False,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    apartment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("apartments.id", ondelete="SET NULL")
    )
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("request_categories.id", ondelete="RESTRICT"), nullable=False
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    place: Mapped[str] = mapped_column(String(20), default=RequestPlace.APARTMENT, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=RequestStatus.NEW, nullable=False)
    priority: Mapped[str] = mapped_column(
        String(20), default=RequestPriority.NORMAL, nullable=False
    )

    assigned_to: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rating: Mapped[int | None] = mapped_column(Integer)
    rating_comment: Mapped[str | None] = mapped_column(String(500))

    category: Mapped[RequestCategory] = relationship(lazy="joined")
    attachments: Mapped[list["RequestAttachment"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan"
    )

    @property
    def is_overdue(self) -> bool:
        from datetime import UTC

        if self.sla_due_at is None or self.status in (
            RequestStatus.DONE,
            RequestStatus.CLOSED,
            RequestStatus.REJECTED,
        ):
            return False
        return self.sla_due_at < datetime.now(UTC)


class RequestAttachment(Base, TimestampMixin):
    __tablename__ = "request_attachments"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("service_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), default="image", nullable=False)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class RequestEvent(Base, TimestampMixin):
    """История заявки: смена статусов и переписка."""

    __tablename__ = "request_events"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("service_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    old_status: Mapped[str | None] = mapped_column(String(20))
    new_status: Mapped[str | None] = mapped_column(String(20))
    comment: Mapped[str | None] = mapped_column(Text)
    is_internal: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="Внутренняя заметка, жильцу не видна"
    )
