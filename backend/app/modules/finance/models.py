"""Прозрачность расходов организации.

Самая дешёвая в разработке функция с самым сильным эффектом на доверие:
снимает вечный конфликт «куда ушли наши деньги» и защищает
добросовестного председателя от обвинений.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin
from app.shared.enums import BillingPeriodStatus, BudgetDirection


class BudgetPeriod(Base, TimestampMixin):
    __tablename__ = "budget_periods"
    __table_args__ = (
        UniqueConstraint("complex_id", "year", "month", name="uq_budget_period"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    complex_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("complexes.id", ondelete="CASCADE"), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=BillingPeriodStatus.DRAFT, nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    comment: Mapped[str | None] = mapped_column(Text)

    items: Mapped[list["BudgetItem"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan"
    )


class BudgetItem(Base, TimestampMixin):
    __tablename__ = "budget_items"
    __table_args__ = (Index("ix_budget_items_period", "budget_period_id"),)

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    budget_period_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("budget_periods.id", ondelete="CASCADE"), nullable=False
    )
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False, comment="Тенге")
    spent_at: Mapped[date | None] = mapped_column(Date)
    document_url: Mapped[str | None] = mapped_column(
        String(500), comment="Скан счёта или акта — главное доказательство"
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
