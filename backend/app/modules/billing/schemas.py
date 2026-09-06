"""Схемы модуля начислений и платежей."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


# --------------------------------------------------------------------------
# Справочники
# --------------------------------------------------------------------------


class ServiceTypeIn(BaseModel):
    name: str = Field(max_length=150)
    unit: str | None = Field(default=None, max_length=20)
    is_metered: bool = False
    order_num: int = 0


class ServiceTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    unit: str | None
    is_metered: bool
    order_num: int


class AccountIn(BaseModel):
    apartment_id: uuid.UUID
    external_number: str = Field(max_length=50)


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    apartment_id: uuid.UUID
    external_number: str
    balance: int


# --------------------------------------------------------------------------
# Периоды и начисления
# --------------------------------------------------------------------------


class BillingPeriodIn(BaseModel):
    year: int = Field(ge=2020, le=2100)
    month: int = Field(ge=1, le=12)
    due_date: date | None = None


class BillingPeriodOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    year: int
    month: int
    status: str
    due_date: date | None
    published_at: datetime | None


class ChargeIn(BaseModel):
    """Одна строка начисления при импорте."""

    account_number: str = Field(description="Номер лицевого счёта в биллинге организации")
    service_name: str
    amount: int = Field(ge=0, description="Сумма в тенге, без копеек")
    volume: Decimal | None = None
    tariff: Decimal | None = None


class ChargeImportIn(BaseModel):
    period_id: uuid.UUID
    charges: list[ChargeIn] = Field(min_length=1, max_length=20000)


class ChargeImportOut(BaseModel):
    imported: int
    skipped_unknown_account: list[str]
    created_service_types: list[str]
    total_amount: int


class ChargeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    service_name: str
    amount: int
    volume: Decimal | None
    tariff: Decimal | None


# --------------------------------------------------------------------------
# Квитанции
# --------------------------------------------------------------------------


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    year: int
    month: int
    total_amount: int
    paid_amount: int
    outstanding: int
    status: str
    due_date: date | None


class InvoiceDetailOut(InvoiceOut):
    account_number: str
    apartment_number: str
    charges: list[ChargeOut]
    pdf_url: str | None


class PublishPeriodOut(BaseModel):
    invoices_created: int
    total_amount: int


# --------------------------------------------------------------------------
# Платежи
# --------------------------------------------------------------------------


class PaymentClaimIn(BaseModel):
    """Жилец сообщает, что оплатил. Подтверждением это ещё не является."""

    amount: int = Field(gt=0)
    paid_at: datetime
    source: str = Field(default="kaspi_deeplink", pattern="^(kaspi_deeplink|manual_receipt|cash)$")
    receipt_url: str | None = Field(default=None, max_length=500)
    receipt_ref: str | None = Field(default=None, max_length=100)


class PaymentClaimOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_id: uuid.UUID
    amount: int
    paid_at: datetime
    status: str
    receipt_url: str | None
    receipt_ref: str | None
    created_at: datetime


class PaymentFactIn(BaseModel):
    """Строка банковского реестра."""

    account_number: str = Field(max_length=50)
    amount: int = Field(gt=0)
    paid_at: datetime
    external_ref: str = Field(max_length=100)
    payer_name: str | None = None
    comment: str | None = None


class PaymentRegistryImportIn(BaseModel):
    source: str = Field(default="bank_statement", pattern="^(kaspi_registry|bank_statement|manual)$")
    payments: list[PaymentFactIn] = Field(min_length=1, max_length=20000)


class PaymentRegistryImportOut(BaseModel):
    imported: int
    duplicates_skipped: int
    matched_invoices: int
    unrecognized_accounts: list[str]
    total_amount: int


class PaymentFactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID | None
    raw_account_number: str | None
    amount: int
    unallocated_amount: int
    paid_at: datetime
    external_ref: str
    payer_name: str | None
    is_matched: bool


class ManualMatchIn(BaseModel):
    """Ручная привязка платежа к квитанции на экране сверки."""

    invoice_id: uuid.UUID
    amount: int | None = Field(default=None, gt=0, description="По умолчанию — весь остаток")


class DebtorOut(BaseModel):
    apartment_number: str
    building_number: str
    account_number: str
    debt: int
    overdue_invoices: int
