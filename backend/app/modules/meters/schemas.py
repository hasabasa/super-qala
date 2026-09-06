"""Схемы приборов учёта."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class MeterIn(BaseModel):
    apartment_id: uuid.UUID
    type: str = Field(pattern="^(cold_water|hot_water|electricity|gas|heating)$")
    serial_number: str | None = Field(default=None, max_length=50)
    installed_at: date | None = None
    next_check_at: date | None = None
    decimals: int = Field(default=0, ge=0, le=3)


class MeterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    apartment_id: uuid.UUID
    type: str
    serial_number: str | None
    next_check_at: date | None
    check_overdue: bool
    decimals: int


class MeterWithLastOut(MeterOut):
    last_value: Decimal | None
    last_period: str | None
    needs_reading: bool


class ReadingIn(BaseModel):
    value: Decimal = Field(ge=0, le=99999999)
    photo_url: str | None = Field(default=None, max_length=500)
    ocr_value: Decimal | None = None
    ocr_confidence: Decimal | None = Field(default=None, ge=0, le=1)
    period_year: int | None = Field(default=None, ge=2020, le=2100)
    period_month: int | None = Field(default=None, ge=1, le=12)


class ReadingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    meter_id: uuid.UUID
    value: Decimal
    previous_value: Decimal | None
    consumption: Decimal | None
    is_anomaly: bool
    status: str
    source: str
    photo_url: str | None
    period_year: int
    period_month: int
    created_at: datetime


class ReadingsExportRow(BaseModel):
    apartment_number: str
    building_number: str
    meter_type: str
    serial_number: str | None
    previous_value: Decimal | None
    value: Decimal
    consumption: Decimal | None
    is_anomaly: bool
