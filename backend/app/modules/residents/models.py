"""Привязка жильца к квартире и её подтверждение.

Подтверждение квартиры — точка наивысшего риска в системе: оно открывает
доступ к финансовым данным и к чату соседей. Поэтому подтверждённая
привязка всегда хранит способ и того, кто подтвердил.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin
from app.modules.properties.models import Apartment
from app.shared.enums import ResidentRelation, ResidentStatus


class ApartmentResident(Base, TimestampMixin):
    """Связь пользователя с квартирой.

    Арендаторы и члены семьи не видят начислений — только чат и заявки.
    """

    __tablename__ = "apartment_residents"
    __table_args__ = (
        UniqueConstraint("user_id", "apartment_id", name="uq_resident_apartment"),
        Index("ix_apartment_residents_apartment", "apartment_id"),
        Index("ix_apartment_residents_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    apartment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("apartments.id", ondelete="CASCADE"), nullable=False
    )
    relation: Mapped[str] = mapped_column(
        String(20), default=ResidentRelation.OWNER, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default=ResidentStatus.PENDING, nullable=False
    )
    verification_method: Mapped[str | None] = mapped_column(String(20))
    verified_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invited_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    rejection_reason: Mapped[str | None] = mapped_column(String(300))

    apartment: Mapped[Apartment] = relationship(lazy="joined")

    @property
    def can_see_billing(self) -> bool:
        """Начисления видит только подтверждённый собственник."""
        return (
            self.status == ResidentStatus.VERIFIED
            and self.relation == ResidentRelation.OWNER
        )


class ApartmentVerificationCode(Base, TimestampMixin):
    """Код с бумажной квитанции — самый быстрый способ подтвердить квартиру.

    Генерируется управляющей организацией и печатается на квитанции.
    Одноразовый.
    """

    __tablename__ = "apartment_verification_codes"
    __table_args__ = (
        UniqueConstraint("apartment_id", "code", name="uq_apartment_code"),
        Index("ix_apartment_verification_codes_code", "code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    apartment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("apartments.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(12), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    used_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def is_available(self) -> bool:
        from datetime import UTC

        if self.used_at is not None:
            return False
        return self.expires_at is None or self.expires_at > datetime.now(UTC)
