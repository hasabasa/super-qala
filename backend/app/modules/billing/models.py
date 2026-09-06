"""Начисления, квитанции и платежи.

Ключевой принцип модуля: деньги через нас не проходят. Жилец платит
напрямую на счёт организации, мы лишь фиксируем факт.

Отсюда две независимые сущности:
  PaymentClaim — «я оплатил» со слов жильца, с приложенным чеком;
  PaymentFact  — подтверждённый платёж из банковского реестра.

Источник истины — всегда PaymentFact. Если их смешать, через месяц
в системе появятся «оплаченные» долги.

Все суммы — целые тенге, без копеек.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin
from app.shared.enums import (
    BillingPeriodStatus,
    InvoiceStatus,
    PaymentClaimStatus,
)


class ServiceType(Base, TimestampMixin):
    """Вид услуги: содержание дома, холодная вода, вывоз мусора и т. д."""

    __tablename__ = "service_types"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_service_type_name"),
        Index("ix_service_types_organization", "organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(20), comment="м3, кВт·ч, м2, мес")
    is_metered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    order_num: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Account(Base, TimestampMixin):
    """Лицевой счёт квартиры.

    external_number — номер в биллинге организации. Именно по нему
    приходит платёж из банка, поэтому он же и ключ сверки.
    """

    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("organization_id", "external_number", name="uq_account_external"),
        Index("ix_accounts_apartment", "apartment_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    apartment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("apartments.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    external_number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    balance: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="Отрицательный — задолженность"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class BillingPeriod(Base, TimestampMixin):
    """Расчётный месяц. Пока черновик — жильцы квитанций не видят."""

    __tablename__ = "billing_periods"
    __table_args__ = (
        UniqueConstraint("organization_id", "year", "month", name="uq_billing_period"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=BillingPeriodStatus.DRAFT, nullable=False
    )
    due_date: Mapped[date | None] = mapped_column(Date)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Charge(Base, TimestampMixin):
    """Одна строка квитанции."""

    __tablename__ = "charges"
    __table_args__ = (
        Index("ix_charges_invoice", "invoice_id"),
        Index("ix_charges_period_account", "billing_period_id", "account_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    billing_period_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("billing_periods.id", ondelete="CASCADE"), nullable=False
    )
    service_type_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("service_types.id", ondelete="RESTRICT"), nullable=False
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE")
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False, comment="Тенге")
    volume: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    tariff: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))

    service_type: Mapped[ServiceType] = relationship(lazy="joined")


class Invoice(Base, TimestampMixin):
    """Квитанция: все начисления лицевого счёта за период."""

    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("account_id", "billing_period_id", name="uq_invoice_account_period"),
        Index("ix_invoices_status", "status"),
        Index("ix_invoices_account", "account_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    billing_period_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("billing_periods.id", ondelete="CASCADE"), nullable=False
    )
    total_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    paid_amount: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(25), default=InvoiceStatus.ISSUED, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    pdf_url: Mapped[str | None] = mapped_column(String(500))

    charges: Mapped[list[Charge]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", foreign_keys=[Charge.invoice_id]
    )

    @property
    def outstanding(self) -> int:
        """Сколько осталось заплатить."""
        return max(self.total_amount - self.paid_amount, 0)


class PaymentClaim(Base, TimestampMixin):
    """Заявление жильца об оплате. Не является подтверждением платежа."""

    __tablename__ = "payment_claims"
    __table_args__ = (Index("ix_payment_claims_invoice", "invoice_id"),)

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    receipt_url: Mapped[str | None] = mapped_column(String(500))
    receipt_ref: Mapped[str | None] = mapped_column(
        String(100), comment="Номер операции из чека Kaspi"
    )
    source: Mapped[str] = mapped_column(String(25), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=PaymentClaimStatus.PENDING, nullable=False
    )
    matched_fact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payment_facts.id", ondelete="SET NULL")
    )


class PaymentFact(Base, TimestampMixin):
    """Подтверждённый платёж из банковского реестра. Источник истины."""

    __tablename__ = "payment_facts"
    __table_args__ = (
        UniqueConstraint("organization_id", "external_ref", name="uq_payment_fact_ref"),
        Index("ix_payment_facts_account", "account_id"),
        Index("ix_payment_facts_unmatched", "organization_id", "is_matched"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"),
        comment="NULL, если лицевой счёт из реестра не опознан",
    )
    raw_account_number: Mapped[str | None] = mapped_column(
        String(50), comment="Номер счёта как он пришёл в реестре"
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    external_ref: Mapped[str] = mapped_column(String(100), nullable=False)
    source: Mapped[str] = mapped_column(String(25), nullable=False)
    payer_name: Mapped[str | None] = mapped_column(String(200))
    comment: Mapped[str | None] = mapped_column(Text)
    is_matched: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    unallocated_amount: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="Не разнесённый по квитанциям остаток"
    )


class ReconciliationEntry(Base, TimestampMixin):
    """Журнал сверки: что и как было сопоставлено."""

    __tablename__ = "reconciliation_log"
    __table_args__ = (Index("ix_reconciliation_invoice", "invoice_id"),)

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_fact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payment_facts.id", ondelete="CASCADE")
    )
    payment_claim_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payment_claims.id", ondelete="CASCADE")
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE")
    )
    action: Mapped[str] = mapped_column(String(25), nullable=False)
    amount: Mapped[int | None] = mapped_column(Integer)
    performed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str | None] = mapped_column(String(300))


class PaymentMethod(Base, TimestampMixin):
    """Способ оплаты, настроенный организацией.

    Платёжный провайдер сознательно не зашит в систему. Организация
    указывает свои реквизиты, QR или ссылку — приложение показывает
    то, что настроено. Заменить провайдера можно без изменения кода.
    """

    __tablename__ = "payment_methods"
    __table_args__ = (Index("ix_payment_methods_org", "organization_id"),)

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    instructions: Mapped[str | None] = mapped_column(
        Text, comment="Что сделать жильцу — показывается на экране оплаты"
    )
    requisites: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, comment="Произвольные реквизиты: банк, ИИК, БИК, получатель"
    )
    qr_url: Mapped[str | None] = mapped_column(String(500))
    deeplink_template: Mapped[str | None] = mapped_column(
        String(500),
        comment="Шаблон ссылки с подстановками {account}, {amount}, {period}",
    )
    order_num: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
