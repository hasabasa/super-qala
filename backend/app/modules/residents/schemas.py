"""Схемы модуля привязки жильцов к квартирам."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LinkByCodeIn(BaseModel):
    """Привязка по коду с бумажной квитанции — подтверждается автоматически."""

    apartment_id: uuid.UUID
    code: str = Field(max_length=12)


class LinkRequestIn(BaseModel):
    """Заявка на привязку. Подтверждает администратор организации."""

    apartment_id: uuid.UUID
    relation: str = Field(default="owner", pattern="^(owner|tenant|family_member)$")


class InviteResidentIn(BaseModel):
    """Приглашение жильца собственником — для арендаторов и членов семьи."""

    apartment_id: uuid.UUID
    phone: str
    relation: str = Field(default="family_member", pattern="^(tenant|family_member)$")


class RejectIn(BaseModel):
    reason: str = Field(max_length=300)


class ApartmentBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: str
    floor: int | None


class ResidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    apartment_id: uuid.UUID
    relation: str
    status: str
    verification_method: str | None
    verified_at: datetime | None
    created_at: datetime


class MyApartmentOut(ResidentOut):
    apartment: ApartmentBrief
    complex_name: str
    building_number: str
    can_see_billing: bool


class PendingResidentOut(ResidentOut):
    """Заявка в списке администратора организации."""

    user_phone: str
    user_name: str
    apartment_number: str
    building_number: str
