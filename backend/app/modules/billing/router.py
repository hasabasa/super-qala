"""Эндпоинты начислений и платежей.

Разделены на два блока: то, что видит жилец, и то, чем управляет
организация. Жилец видит квитанции только по квартирам, где он
подтверждённый собственник.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.deps import CurrentUser, DbSession, Scope
from app.core.exceptions import PermissionDeniedError
from app.modules.billing.models import Account
from app.modules.billing.schemas import (
    AccountIn,
    AccountOut,
    BillingPeriodIn,
    BillingPeriodOut,
    ChargeImportIn,
    ChargeImportOut,
    ChargeOut,
    DebtorOut,
    InvoiceDetailOut,
    InvoiceOut,
    ManualMatchIn,
    PaymentClaimIn,
    PaymentClaimOut,
    PaymentFactOut,
    PaymentRegistryImportIn,
    PaymentRegistryImportOut,
    PublishPeriodOut,
    ServiceTypeIn,
    ServiceTypeOut,
)
from app.modules.billing.service import BillingService
from app.modules.properties.service import PropertiesService
from app.modules.residents.service import ResidentsService

router = APIRouter(tags=["billing"])


def get_service(session: DbSession) -> BillingService:
    return BillingService(session)


ServiceDep = Annotated[BillingService, Depends(get_service)]


async def _billing_apartments(session: DbSession, user_id: uuid.UUID) -> set[uuid.UUID]:
    """Квартиры, по которым пользователь вправе видеть начисления."""
    residents = ResidentsService(session)
    rows = await residents.list_my_apartments(user_id)
    return {r.apartment_id for r, _, _ in rows if r.can_see_billing}


# ======================================================================
# Жилец
# ======================================================================


@router.get("/billing/invoices", response_model=list[InvoiceOut], summary="Мои квитанции")
async def list_my_invoices(
    user: CurrentUser,
    service: ServiceDep,
    session: DbSession,
    year: Annotated[int | None, Query(ge=2020, le=2100)] = None,
) -> list[InvoiceOut]:
    apartment_ids = await _billing_apartments(session, user.id)
    rows = await service.list_invoices_for_apartments(apartment_ids, year)
    return [
        InvoiceOut(
            id=inv.id,
            account_id=inv.account_id,
            year=period.year,
            month=period.month,
            total_amount=inv.total_amount,
            paid_amount=inv.paid_amount,
            outstanding=inv.outstanding,
            status=inv.status,
            due_date=inv.due_date,
        )
        for inv, period, _ in rows
    ]


@router.get(
    "/billing/invoices/{invoice_id}",
    response_model=InvoiceDetailOut,
    summary="Квитанция с разбивкой по услугам",
)
async def get_invoice(
    invoice_id: uuid.UUID, user: CurrentUser, service: ServiceDep, session: DbSession
) -> InvoiceDetailOut:
    apartment_id = await service.get_invoice_apartment(invoice_id)
    if apartment_id not in await _billing_apartments(session, user.id):
        raise PermissionDeniedError("Нет доступа к этой квитанции")

    invoice = await service.get_invoice(invoice_id)
    period = await service.get_period(invoice.billing_period_id)
    properties = PropertiesService(session)
    apartment = await properties.get_apartment(apartment_id)
    account = await session.get(Account, invoice.account_id)

    return InvoiceDetailOut(
        id=invoice.id,
        account_id=invoice.account_id,
        year=period.year,
        month=period.month,
        total_amount=invoice.total_amount,
        paid_amount=invoice.paid_amount,
        outstanding=invoice.outstanding,
        status=invoice.status,
        due_date=invoice.due_date,
        account_number=account.external_number if account else "",
        apartment_number=apartment.number,
        pdf_url=invoice.pdf_url,
        charges=[
            ChargeOut(
                id=c.id,
                service_name=c.service_type.name,
                amount=c.amount,
                volume=c.volume,
                tariff=c.tariff,
            )
            for c in invoice.charges
        ],
    )


@router.post(
    "/billing/invoices/{invoice_id}/payment-claim",
    response_model=PaymentClaimOut,
    status_code=status.HTTP_201_CREATED,
    summary="Сообщить об оплате и приложить чек",
)
async def create_payment_claim(
    invoice_id: uuid.UUID,
    payload: PaymentClaimIn,
    user: CurrentUser,
    service: ServiceDep,
    session: DbSession,
) -> PaymentClaimOut:
    apartment_id = await service.get_invoice_apartment(invoice_id)
    if apartment_id not in await _billing_apartments(session, user.id):
        raise PermissionDeniedError("Нет доступа к этой квитанции")
    claim = await service.create_payment_claim(invoice_id, user.id, payload)
    return PaymentClaimOut.model_validate(claim)


# ======================================================================
# Организация
# ======================================================================


@router.post(
    "/organizations/{organization_id}/service-types",
    response_model=ServiceTypeOut,
    status_code=status.HTTP_201_CREATED,
    summary="Завести вид услуги",
)
async def create_service_type(
    organization_id: uuid.UUID, payload: ServiceTypeIn, service: ServiceDep, scope: Scope
) -> ServiceTypeOut:
    service.ensure_access(organization_id, scope)
    return ServiceTypeOut.model_validate(
        await service.create_service_type(organization_id, payload)
    )


@router.get("/organizations/{organization_id}/service-types", response_model=list[ServiceTypeOut])
async def list_service_types(
    organization_id: uuid.UUID, service: ServiceDep, scope: Scope
) -> list[ServiceTypeOut]:
    service.ensure_access(organization_id, scope)
    return [
        ServiceTypeOut.model_validate(s) for s in await service.list_service_types(organization_id)
    ]


@router.post(
    "/organizations/{organization_id}/accounts",
    response_model=AccountOut,
    status_code=status.HTTP_201_CREATED,
    summary="Завести лицевой счёт",
)
async def create_account(
    organization_id: uuid.UUID, payload: AccountIn, service: ServiceDep, scope: Scope
) -> AccountOut:
    service.ensure_access(organization_id, scope)
    return AccountOut.model_validate(await service.create_account(organization_id, payload))


@router.post(
    "/organizations/{organization_id}/billing-periods",
    response_model=BillingPeriodOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать расчётный период",
)
async def create_period(
    organization_id: uuid.UUID, payload: BillingPeriodIn, service: ServiceDep, scope: Scope
) -> BillingPeriodOut:
    service.ensure_access(organization_id, scope)
    return BillingPeriodOut.model_validate(await service.create_period(organization_id, payload))


@router.get(
    "/organizations/{organization_id}/billing-periods", response_model=list[BillingPeriodOut]
)
async def list_periods(
    organization_id: uuid.UUID, service: ServiceDep, scope: Scope
) -> list[BillingPeriodOut]:
    service.ensure_access(organization_id, scope)
    return [BillingPeriodOut.model_validate(p) for p in await service.list_periods(organization_id)]


@router.post(
    "/organizations/{organization_id}/charges/import",
    response_model=ChargeImportOut,
    summary="Загрузить начисления в черновик периода",
)
async def import_charges(
    organization_id: uuid.UUID, payload: ChargeImportIn, service: ServiceDep, scope: Scope
) -> ChargeImportOut:
    service.ensure_access(organization_id, scope)
    return await service.import_charges(organization_id, payload)


@router.post(
    "/organizations/{organization_id}/billing-periods/{period_id}/publish",
    response_model=PublishPeriodOut,
    summary="Опубликовать период и разослать квитанции",
)
async def publish_period(
    organization_id: uuid.UUID, period_id: uuid.UUID, service: ServiceDep, scope: Scope
) -> PublishPeriodOut:
    service.ensure_access(organization_id, scope)
    created, total = await service.publish_period(organization_id, period_id)
    return PublishPeriodOut(invoices_created=created, total_amount=total)


@router.post(
    "/organizations/{organization_id}/payments/import",
    response_model=PaymentRegistryImportOut,
    summary="Загрузить банковский реестр и провести сверку",
)
async def import_payments(
    organization_id: uuid.UUID,
    payload: PaymentRegistryImportIn,
    service: ServiceDep,
    scope: Scope,
) -> PaymentRegistryImportOut:
    service.ensure_access(organization_id, scope)
    return await service.import_payment_registry(organization_id, payload)


@router.get(
    "/organizations/{organization_id}/payments/unmatched",
    response_model=list[PaymentFactOut],
    summary="Платежи, не разнесённые автоматически",
)
async def list_unmatched(
    organization_id: uuid.UUID, service: ServiceDep, scope: Scope
) -> list[PaymentFactOut]:
    service.ensure_access(organization_id, scope)
    return [
        PaymentFactOut.model_validate(f) for f in await service.list_unmatched_facts(organization_id)
    ]


@router.post(
    "/organizations/{organization_id}/payments/{fact_id}/match",
    response_model=PaymentFactOut,
    summary="Привязать платёж к квитанции вручную",
)
async def manual_match(
    organization_id: uuid.UUID,
    fact_id: uuid.UUID,
    payload: ManualMatchIn,
    user: CurrentUser,
    service: ServiceDep,
    scope: Scope,
) -> PaymentFactOut:
    service.ensure_access(organization_id, scope)
    fact = await service.manual_match(
        organization_id, fact_id, payload.invoice_id, payload.amount, user.id
    )
    return PaymentFactOut.model_validate(fact)


@router.get(
    "/organizations/{organization_id}/debtors",
    response_model=list[DebtorOut],
    summary="Реестр задолженности",
)
async def list_debtors(
    organization_id: uuid.UUID, service: ServiceDep, scope: Scope
) -> list[DebtorOut]:
    service.ensure_access(organization_id, scope)
    return [DebtorOut(**row) for row in await service.list_debtors(organization_id)]


@router.get(
    "/organizations/{organization_id}/billing-periods/{period_id}/summary",
    summary="Собираемость за период",
)
async def collection_summary(
    organization_id: uuid.UUID, period_id: uuid.UUID, service: ServiceDep, scope: Scope
) -> dict:
    service.ensure_access(organization_id, scope)
    return await service.collection_summary(organization_id, period_id)
