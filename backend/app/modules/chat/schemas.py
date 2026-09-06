"""Схемы чата."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AttachmentIn(BaseModel):
    file_url: str = Field(max_length=500)
    file_type: str = Field(default="image", pattern="^(image|video|document)$")
    width: int | None = None
    height: int | None = None
    size_bytes: int | None = None


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    file_url: str
    file_type: str
    width: int | None
    height: int | None


class AuthorOut(BaseModel):
    id: uuid.UUID
    name: str
    avatar_url: str | None


class MessageIn(BaseModel):
    text: str | None = Field(default=None, max_length=4000)
    reply_to_id: uuid.UUID | None = None
    attachments: list[AttachmentIn] = Field(default_factory=list, max_length=10)
    is_important: bool = Field(
        default=False, description="Важное объявление. Доступно только сотрудникам организации"
    )


class MessageOut(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    author: AuthorOut
    text: str | None
    reply_to_id: uuid.UUID | None
    is_pinned: bool
    is_important: bool
    is_deleted: bool
    attachments: list[AttachmentOut]
    created_at: datetime


class MessagePage(BaseModel):
    """Курсорная страница: обычный offset на живой ленте разъезжается."""

    items: list[MessageOut]
    next_cursor: str | None


class ChannelOut(BaseModel):
    id: uuid.UUID
    type: str
    name: str
    is_readonly: bool
    can_write: bool
    unread_count: int
    last_message: MessageOut | None


class MarkReadIn(BaseModel):
    last_read_at: datetime | None = None


class MuteIn(BaseModel):
    user_id: uuid.UUID
    hours: int = Field(default=24, ge=1, le=8760)
