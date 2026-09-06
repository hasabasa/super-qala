"""Схемы доски объявлений."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PhotoIn(BaseModel):
    file_url: str = Field(max_length=500)


class PhotoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    file_url: str
    order_num: int


class ListingIn(BaseModel):
    complex_id: uuid.UUID
    type: str = Field(default="sell", pattern="^(sell|buy|service|give_away)$")
    category: str = Field(max_length=50)
    title: str = Field(max_length=200, min_length=3)
    description: str = Field(min_length=5)
    price: int | None = Field(default=None, ge=0)
    photos: list[PhotoIn] = Field(default_factory=list, max_length=5)


class ListingUpdateIn(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = None
    price: int | None = Field(default=None, ge=0)
    status: str | None = Field(default=None, pattern="^(active|archived|sold)$")


class ListingOut(BaseModel):
    id: uuid.UUID
    type: str
    category: str
    title: str
    description: str
    price: int | None
    status: str
    views_count: int
    is_pinned: bool
    is_highlighted: bool
    author_name: str
    photos: list[PhotoOut]
    created_at: datetime


class ContactOut(BaseModel):
    phone: str
    author_name: str


class PromoteIn(BaseModel):
    type: str = Field(pattern="^(pin_top|highlight)$")
    days: int = Field(default=7, ge=1, le=30)


class PromoteOut(BaseModel):
    id: uuid.UUID
    type: str
    amount: int
    days: int
    ends_at: datetime
    is_paid: bool
    payment_hint: str


class BlockIn(BaseModel):
    reason: str = Field(max_length=300)
