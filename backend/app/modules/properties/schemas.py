"""Схемы модуля недвижимости."""

import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ApartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: str
    floor: int | None
    area_sqm: Decimal | None
    rooms_count: int | None


class EntranceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: int


class BuildingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: str
    floors_count: int | None


class ComplexOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    address: str
    city: str


class ComplexSearchOut(ComplexOut):
    organization_name: str


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    bin: str | None
    type: str
    phone: str | None
    tariff: str
    status: str


class OrganizationCreateIn(BaseModel):
    name: str = Field(max_length=200)
    bin: str | None = Field(default=None, max_length=12)
    type: str = Field(default="osi", pattern="^(osi|ksk|uk)$")
    phone: str | None = None
    email: str | None = None
    address: str | None = None


class ComplexCreateIn(BaseModel):
    name: str = Field(max_length=200)
    address: str = Field(max_length=300)
    city: str = "Астана"


class BuildingCreateIn(BaseModel):
    number: str = Field(max_length=20)
    floors_count: int | None = Field(default=None, ge=1, le=100)


class EntranceCreateIn(BaseModel):
    number: int = Field(ge=1, le=100)


class ApartmentCreateIn(BaseModel):
    number: str = Field(max_length=10)
    floor: int | None = Field(default=None, ge=-5, le=100)
    area_sqm: Decimal | None = Field(default=None, gt=0, le=10000)
    rooms_count: int | None = Field(default=None, ge=1, le=20)


class ApartmentBulkCreateIn(BaseModel):
    """Массовое создание квартир в подъезде.

    Типовой сценарий заведения дома: подъезд, этажи, квартир на этаже.
    """

    entrance_id: uuid.UUID
    start_number: int = Field(ge=1)
    count: int = Field(ge=1, le=500)
    apartments_per_floor: int = Field(default=4, ge=1, le=50)
    first_floor: int = Field(default=1)


class GrantRoleIn(BaseModel):
    """Назначение сотрудника организации. Пользователь создаётся, если его ещё нет."""

    phone: str
    role: str = Field(
        default="osi_admin", pattern="^(osi_admin|osi_moderator|osi_finance)$"
    )


class GrantRoleOut(BaseModel):
    user_id: uuid.UUID
    phone: str
    role: str
