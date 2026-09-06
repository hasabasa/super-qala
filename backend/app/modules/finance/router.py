"""Эндпоинты прозрачности расходов."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.deps import CurrentUser, DbSession, Scope
from app.modules.finance.schemas import (
    BudgetItemIn,
    BudgetItemOut,
    BudgetPeriodDetailOut,
    BudgetPeriodIn,
    BudgetPeriodOut,
)
from app.modules.finance.service import FinanceService
from app.modules.voting.service import VotingService

router = APIRouter(tags=["finance"])


def get_service(session: DbSession) -> FinanceService:
    return FinanceService(session)


ServiceDep = Annotated[FinanceService, Depends(get_service)]


def _period_out(period, service: FinanceService) -> BudgetPeriodOut:
    income, expense = service.totals(period)
    return BudgetPeriodOut(
        id=period.id,
        year=period.year,
        month=period.month,
        status=period.status,
        published_at=period.published_at,
        comment=period.comment,
        total_income=income,
        total_expense=expense,
        balance=income - expense,
    )


@router.post(
    "/organizations/{organization_id}/budget-periods",
    response_model=BudgetPeriodOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать отчёт за месяц",
)
async def create_period(
    organization_id: uuid.UUID, payload: BudgetPeriodIn, service: ServiceDep, scope: Scope
) -> BudgetPeriodOut:
    scope.ensure(organization_id)
    return _period_out(await service.create_period(organization_id, payload), service)


@router.post(
    "/budget-periods/{period_id}/items",
    response_model=BudgetItemOut,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить статью дохода или расхода",
)
async def add_item(
    period_id: uuid.UUID,
    payload: BudgetItemIn,
    user: CurrentUser,
    service: ServiceDep,
    scope: Scope,
) -> BudgetItemOut:
    period = await service.get_period(period_id)
    scope.ensure(period.organization_id)
    return BudgetItemOut.model_validate(await service.add_item(period_id, payload, user.id))


@router.delete(
    "/budget-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить статью"
)
async def delete_item(item_id: uuid.UUID, service: ServiceDep, scope: Scope) -> None:
    from app.modules.finance.models import BudgetItem

    item = await service.session.get(BudgetItem, item_id)
    if item is not None:
        period = await service.get_period(item.budget_period_id)
        scope.ensure(period.organization_id)
    await service.delete_item(item_id)


@router.post(
    "/budget-periods/{period_id}/publish",
    response_model=BudgetPeriodOut,
    summary="Опубликовать отчёт жильцам",
)
async def publish(period_id: uuid.UUID, service: ServiceDep, scope: Scope) -> BudgetPeriodOut:
    period = await service.get_period(period_id)
    scope.ensure(period.organization_id)
    return _period_out(await service.publish(period_id), service)


@router.get(
    "/complexes/{complex_id}/budget-periods",
    response_model=list[BudgetPeriodOut],
    summary="Отчёты ЖК",
)
async def list_periods(
    complex_id: uuid.UUID, service: ServiceDep, scope: Scope, _: CurrentUser
) -> list[BudgetPeriodOut]:
    organization_id = await VotingService(service.session).organization_of(complex_id)
    published_only = not scope.allows(organization_id)
    periods = await service.list_periods(complex_id, published_only)
    return [_period_out(p, service) for p in periods]


@router.get(
    "/budget-periods/{period_id}",
    response_model=BudgetPeriodDetailOut,
    summary="Отчёт с разбивкой по категориям",
)
async def get_period(
    period_id: uuid.UUID, service: ServiceDep, scope: Scope, _: CurrentUser
) -> BudgetPeriodDetailOut:
    from app.core.exceptions import PermissionDeniedError
    from app.shared.enums import BillingPeriodStatus

    period = await service.get_period(period_id)
    if period.status != BillingPeriodStatus.PUBLISHED and not scope.allows(period.organization_id):
        raise PermissionDeniedError("Отчёт ещё не опубликован")

    base = _period_out(period, service)
    return BudgetPeriodDetailOut(
        **base.model_dump(),
        items=[BudgetItemOut.model_validate(i) for i in period.items],
        by_category=service.by_category(period),
    )
