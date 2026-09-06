"""Устройства и история уведомлений.

Push — исчерпаемый ресурс: каждое лишнее уведомление приближает момент,
когда пользователь отключит их навсегда. Поэтому у каждого типа есть
отдельный переключатель, а история хранится целиком.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin
from app.shared.enums import NotificationChannel, NotificationStatus


class Device(Base, TimestampMixin):
    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("fcm_token", name="uq_device_token"),)

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fcm_token: Mapped[str] = mapped_column(String(500), nullable=False)
    platform: Mapped[str] = mapped_column(String(10), nullable=False)
    app_version: Mapped[str | None] = mapped_column(String(20))
    locale: Mapped[str] = mapped_column(String(2), default="ru", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationPreference(Base, TimestampMixin):
    """Переключатель по типу уведомлений. Отсутствие записи означает «включено»."""

    __tablename__ = "notification_preferences"
    __table_args__ = (UniqueConstraint("user_id", "type", name="uq_notification_pref"),)

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    push_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_created", "user_id", "created_at"),
        Index("ix_notifications_unread", "user_id", "read_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, comment="Данные для перехода: тип объекта и его идентификатор"
    )
    channel: Mapped[str] = mapped_column(
        String(10), default=NotificationChannel.PUSH, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(10), default=NotificationStatus.PENDING, nullable=False
    )
    error: Mapped[str | None] = mapped_column(String(300))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
