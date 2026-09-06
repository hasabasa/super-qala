"""Публикация доходов и расходов организации."""

import uuid
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.modules.finance.models import BudgetItem, BudgetPeriod
from app.modules.finance.schemas import BudgetItemIn, BudgetPeriodIn
from app.shared.enums import BillingPeriodStatus, BudgetDirection


class FinanceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_period(
        self, organization_id: uuid.UUID, payload: BudgetPeriodIn
    ) -> BudgetPeriod:
        exists = await self.session.scalar(
            select(BudgetPeriod.id).where(
                BudgetPeriod.complex_id == payload.complex_id,
                BudgetPeriod.year == payload.year,
                BudgetPeriod.month == payload.month,
            )
        )
        if exists:
            raise ConflictError("Отчёт за этот месяц уже создан")

        period = BudgetPeriod(organization_id=organization_id, **payload.model_dump())
        self.session.add(period)
        await self.session.flush()
        # Коллекция статей у нового объекта не загружена: без явного
        # обновления обращение к ней уводит в ленивую подгрузку вне
        # асинхронного контекста и падает с MissingGreenlet.
        await self.session.refresh(period, attribute_names=["items"])
        return period

    async def get_period(self, period_id: uuid.UUID) -> BudgetPeriod:
        period = await self.session.get(BudgetPeriod, period_id)
        if period is None:
            raise NotFoundError("Отчётный период не найден")
        return period

    async def add_item(self, period_id: uuid.UUID, payload: BudgetItemIn, author_id: uuid.UUID) -> BudgetItem:
        period = await self.get_period(period_id)
        if period.status != BillingPeriodStatus.DRAFT:
            raise ConflictError("Опубликованный отчёт изменить нельзя")

        item = BudgetItem(budget_period_id=period_id, created_by=author_id, **payload.model_dump())
        self.session.add(item)
        await self.session.flush()
        return item

    async def delete_item(self, item_id: uuid.UUID) -> None:
        item = await self.session.get(BudgetItem, item_id)
        if item is None:
            raise NotFoundError("Статья не найдена")
        period = await self.get_period(item.budget_period_id)
        if period.status != BillingPeriodStatus.DRAFT:
            raise ConflictError("Опубликованный отчёт изменить нельзя")
        await self.session.delete(item)
        await self.session.flush()

    async def publish(self, period_id: uuid.UUID) -> BudgetPeriod:
        period = await self.get_period(period_id)
        if period.status != BillingPeriodStatus.DRAFT:
            raise ConflictError("Отчёт уже опубликован")
        if not period.items:
            raise ConflictError("В отчёте нет ни одной статьи")

        period.status = BillingPeriodStatus.PUBLISHED
        period.published_at = datetime.now(UTC)
        await self.session.flush()
        await self.session.refresh(period, attribute_names=["items"])
        return period

    async def list_periods(
        self, complex_id: uuid.UUID, published_only: bool
    ) -> list[BudgetPeriod]:
        query = (
            select(BudgetPeriod)
            .where(BudgetPeriod.complex_id == complex_id)
            .order_by(BudgetPeriod.year.desc(), BudgetPeriod.month.desc())
        )
        if published_only:
            query = query.where(BudgetPeriod.status == BillingPeriodStatus.PUBLISHED)
        return list((await self.session.scalars(query)).all())

    @staticmethod
    def totals(period: BudgetPeriod) -> tuple[int, int]:
        income = sum(i.amount for i in period.items if i.direction == BudgetDirection.INCOME)
        expense = sum(i.amount for i in period.items if i.direction == BudgetDirection.EXPENSE)
        return income, expense

    @staticmethod
    def by_category(period: BudgetPeriod) -> dict[str, int]:
        """Разбивка расходов по категориям — то, что смотрят жильцы."""
        grouped: dict[str, int] = defaultdict(int)
        for item in period.items:
            if item.direction == BudgetDirection.EXPENSE:
                grouped[item.category] += item.amount
        return dict(sorted(grouped.items(), key=lambda kv: kv[1], reverse=True))
