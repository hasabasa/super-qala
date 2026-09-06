"""Эндпоинты привязки жильцов к квартирам."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.deps import CurrentUser, DbSession, OrganizationScope
from app.modules.properties.service import PropertiesService
from app.modules.residents.schemas import (
    ApartmentBrief,
    InviteResidentIn,
    LinkByCodeIn,
    LinkRequestIn,
    MyApartmentOut,
    PendingResidentOut,
    RejectIn,
    ResidentOut,
)
from app.modules.residents.service import ResidentsService

router = APIRouter(tags=["residents"])


def get_service(session: DbSession) -> ResidentsService:
    return ResidentsService(session)


ServiceDep = Annotated[ResidentsService, Depends(get_service)]


@router.post(
    "/residents/link-by-code",
    response_model=ResidentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Привязать квартиру кодом с квитанции",
)
async def link_by_code(
    payload: LinkByCodeIn, user: CurrentUser, service: ServiceDep
) -> ResidentOut:
    return ResidentOut.model_validate(await service.link_by_code(user, payload))


@router.post(
    "/residents/link-request",
    response_model=ResidentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Заявка на привязку с подтверждением администратором",
)
async def create_link_request(
    payload: LinkRequestIn, user: CurrentUser, service: ServiceDep
) -> ResidentOut:
    return ResidentOut.model_validate(await service.create_link_request(user, payload))


@router.post(
    "/residents/invite",
    response_model=ResidentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Пригласить арендатора или члена семьи",
)
async def invite(payload: InviteResidentIn, user: CurrentUser, service: ServiceDep) -> ResidentOut:
    return ResidentOut.model_validate(await service.invite(user, payload))


@router.get(
    "/residents/me/apartments",
    response_model=list[MyApartmentOut],
    summary="Мои квартиры и статусы привязки",
)
async def list_my_apartments(user: CurrentUser, service: ServiceDep) -> list[MyApartmentOut]:
    rows = await service.list_my_apartments(user.id)
    return [
        MyApartmentOut(
            id=resident.id,
            user_id=resident.user_id,
            apartment_id=resident.apartment_id,
            relation=resident.relation,
            status=resident.status,
            verification_method=resident.verification_method,
            verified_at=resident.verified_at,
            created_at=resident.created_at,
            apartment=ApartmentBrief.model_validate(resident.apartment),
            complex_name=complex_.name,
            building_number=building.number,
            can_see_billing=resident.can_see_billing,
        )
        for resident, complex_, building in rows
    ]


@router.get(
    "/organizations/{organization_id}/residents/pending",
    response_model=list[PendingResidentOut],
    summary="Заявки на привязку, ожидающие подтверждения",
)
async def list_pending(
    organization_id: uuid.UUID,
    service: ServiceDep,
    session: DbSession,
    scope: OrganizationScope,
) -> list[PendingResidentOut]:
    PropertiesService(session).ensure_access(organization_id, scope)
    rows = await service.list_pending(organization_id)
    return [
        PendingResidentOut(
            id=resident.id,
            user_id=resident.user_id,
            apartment_id=resident.apartment_id,
            relation=resident.relation,
            status=resident.status,
            verification_method=resident.verification_method,
            verified_at=resident.verified_at,
            created_at=resident.created_at,
            user_phone=user.phone,
            user_name=user.full_name,
            apartment_number=apartment.number,
            building_number=building.number,
        )
        for resident, user, apartment, building in rows
    ]


@router.post(
    "/residents/{resident_id}/approve",
    response_model=ResidentOut,
    summary="Подтвердить заявку",
)
async def approve(
    resident_id: uuid.UUID,
    admin: CurrentUser,
    service: ServiceDep,
    session: DbSession,
    scope: OrganizationScope,
) -> ResidentOut:
    resident = await service.get_resident(resident_id)
    properties = PropertiesService(session)
    organization_id = await properties.get_apartment_organization(resident.apartment_id)
    properties.ensure_access(organization_id, scope)
    return ResidentOut.model_validate(await service.approve(resident_id, admin))


@router.post(
    "/residents/{resident_id}/reject",
    response_model=ResidentOut,
    summary="Отклонить заявку",
)
async def reject(
    resident_id: uuid.UUID,
    payload: RejectIn,
    admin: CurrentUser,
    service: ServiceDep,
    session: DbSession,
    scope: OrganizationScope,
) -> ResidentOut:
    resident = await service.get_resident(resident_id)
    properties = PropertiesService(session)
    organization_id = await properties.get_apartment_organization(resident.apartment_id)
    properties.ensure_access(organization_id, scope)
    return ResidentOut.model_validate(await service.reject(resident_id, admin, payload.reason))
