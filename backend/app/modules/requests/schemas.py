"""Схемы модуля заявок."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CategoryIn(BaseModel):
    name: str = Field(max_length=150)
    sla_hours: int = Field(default=48, ge=1, le=8760)
    order_num: int = 0


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    sla_hours: int
    order_num: int


class AttachmentIn(BaseModel):
    file_url: str = Field(max_length=500)
    file_type: str = Field(default="image", pattern="^(image|video|document)$")


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    file_url: str
    file_type: str


class RequestCreateIn(BaseModel):
    category_id: uuid.UUID
    apartment_id: uuid.UUID
    title: str = Field(max_length=200)
    description: str = Field(min_length=5)
    place: str = Field(default="apartment", pattern="^(apartment|entrance|building|yard)$")
    priority: str = Field(default="normal", pattern="^(low|normal|high|emergency)$")
    attachments: list[AttachmentIn] = Field(default_factory=list, max_length=5)


class RequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: int
    title: str
    description: str
    category_name: str
    place: str
    status: str
    priority: str
    sla_due_at: datetime | None
    is_overdue: bool
    closed_at: datetime | None
    rating: int | None
    created_at: datetime
    attachments: list[AttachmentOut]


class RequestListOut(BaseModel):
    """Компактная карточка для списка."""

    id: uuid.UUID
    number: int
    title: str
    category_name: str
    status: str
    priority: str
    sla_due_at: datetime | None
    is_overdue: bool
    created_at: datetime
    apartment_number: str | None = None
    author_name: str | None = None


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: str
    old_status: str | None
    new_status: str | None
    comment: str | None
    author_id: uuid.UUID | None
    created_at: datetime


class RequestDetailOut(RequestOut):
    events: list[EventOut]
    apartment_number: str | None
    assigned_to: uuid.UUID | None


class StatusChangeIn(BaseModel):
    status: str = Field(pattern="^(accepted|in_progress|done|rejected|closed)$")
    comment: str | None = Field(default=None, max_length=1000)


class CommentIn(BaseModel):
    comment: str = Field(min_length=1, max_length=1000)
    is_internal: bool = False


class AssignIn(BaseModel):
    user_id: uuid.UUID


class RatingIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=500)


class SlaReportOut(BaseModel):
    total: int
    closed_in_time: int
    closed_overdue: int
    open_overdue: int
    open_total: int
    sla_rate: float
    average_hours: float | None
