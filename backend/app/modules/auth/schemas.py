"""Схемы модуля авторизации."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RequestCodeIn(BaseModel):
    phone: str = Field(description="Номер в любом формате, например 87011234567")


class RequestCodeOut(BaseModel):
    expires_in: int = Field(description="Через сколько секунд код перестанет действовать")
    retry_after: int = Field(description="Через сколько секунд можно запросить новый код")
    debug_code: str | None = Field(
        default=None, description="Код. Возвращается только в локальной среде"
    )


class VerifyCodeIn(BaseModel):
    phone: str
    code: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class VerifyCodeOut(TokenPair):
    is_new_user: bool = Field(description="True, если профиль ещё не заполнен")


class RefreshIn(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    phone: str
    first_name: str | None
    last_name: str | None
    avatar_url: str | None
    language: str
    created_at: datetime


class UserUpdateIn(BaseModel):
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    avatar_url: str | None = Field(default=None, max_length=500)
    language: str | None = Field(default=None, pattern="^(ru|kk)$")
