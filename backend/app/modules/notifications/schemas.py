"""Схемы уведомлений."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DeviceIn(BaseModel):
    fcm_token: str = Field(max_length=500)
    platform: str = Field(pattern="^(ios|android|web)$")
    app_version: str | None = Field(default=None, max_length=20)
    locale: str = Field(default="ru", pattern="^(ru|kk)$")


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    platform: str
    app_version: str | None
    is_active: bool


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    title: str
    body: str
    payload: dict[str, Any] | None
    status: str
    read_at: datetime | None
    created_at: datetime


class NotificationPage(BaseModel):
    items: list[NotificationOut]
    unread_count: int
    next_cursor: str | None


class PreferenceIn(BaseModel):
    type: str = Field(max_length=30)
    push_enabled: bool


class PreferenceOut(BaseModel):
    type: str
    push_enabled: bool


class BroadcastIn(BaseModel):
    """Рассылка организации по жильцам ЖК."""

    complex_id: uuid.UUID
    title: str = Field(max_length=200)
    body: str = Field(max_length=1000)


class BroadcastOut(BaseModel):
    recipients: int
    sent: int
