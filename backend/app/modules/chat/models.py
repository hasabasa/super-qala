"""Каналы и сообщения.

Разделение на каналы — не украшение. Один общий чат на триста человек
превращается в помойку за две недели, и люди возвращаются в WhatsApp.
Объявления организации вынесены в отдельный канал только для чтения.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin
from app.shared.enums import ChannelMemberRole, ChannelType


class Channel(Base, TimestampMixin):
    """Канал привязан к ЖК, дому или подъезду — уровень задаёт охват."""

    __tablename__ = "channels"
    __table_args__ = (
        Index("ix_channels_complex", "complex_id"),
        Index("ix_channels_scope", "complex_id", "building_id", "entrance_id", "type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    complex_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("complexes.id", ondelete="CASCADE"), nullable=False
    )
    building_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("buildings.id", ondelete="CASCADE")
    )
    entrance_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("entrances.id", ondelete="CASCADE")
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    is_readonly: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="Писать могут только сотрудники организации"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ChannelMember(Base, TimestampMixin):
    """Явное членство нужно для ограничений и отключения уведомлений.

    Доступ к каналу определяется подтверждённой квартирой, а не этой
    таблицей: она хранит настройки и санкции.
    """

    __tablename__ = "channel_members"
    __table_args__ = (UniqueConstraint("channel_id", "user_id", name="uq_channel_member"),)

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(
        String(20), default=ChannelMemberRole.MEMBER, nullable=False
    )
    muted_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="Ограничение на отправку сообщений"
    )
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Message(Base, TimestampMixin):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_channel_created", "channel_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    text: Mapped[str | None] = mapped_column(Text)
    reply_to_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL")
    )
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_important: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="Важное объявление: уходит push всем"
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    attachments: Mapped[list["MessageAttachment"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan"
    )


class MessageAttachment(Base, TimestampMixin):
    __tablename__ = "message_attachments"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), default="image", nullable=False)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    size_bytes: Mapped[int | None] = mapped_column(Integer)


class MessageRead(Base, TimestampMixin):
    """Отметка прочтения — по одной на пользователя и канал."""

    __tablename__ = "message_reads"
    __table_args__ = (UniqueConstraint("channel_id", "user_id", name="uq_message_read"),)

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    last_read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
