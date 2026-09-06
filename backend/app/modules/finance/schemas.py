"""Схемы прозрачности расходов."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class BudgetPeriodIn(BaseModel):
    complex_id: uuid.UUID
    year: int = Field(ge=2020, le=2100)
    month: int = Field(ge=1, le=12)
    comment: str | None = None


class BudgetItemIn(BaseModel):
    direction: str = Field(pattern="^(income|expense)$")
    category: str = Field(max_length=100)
    title: str = Field(max_length=300)
    amount: int = Field(gt=0, description="Тенге, без копеек")
    spent_at: date | None = None
    document_url: str | None = Field(default=None, max_length=500)


class BudgetItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    direction: str
    category: str
    title: str
    amount: int
    spent_at: date | None
    document_url: str | None


class BudgetPeriodOut(BaseModel):
    id: uuid.UUID
    year: int
    month: int
    status: str
    published_at: datetime | None
    comment: str | None
    total_income: int
    total_expense: int
    balance: int


class BudgetPeriodDetailOut(BudgetPeriodOut):
    items: list[BudgetItemOut]
    by_category: dict[str, int]
