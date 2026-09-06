"""Эндпоинты по организациям и недвижимости.

Публичный только поиск ЖК — он нужен на экране привязки квартиры
до того, как у пользователя появилась организация.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.deps import CurrentUser, DbSession, OrganizationScope, require_roles
from app.modules.auth.models import User
from app.shared.enums import UserRoleType
from app.modules.properties.schemas import (
    ApartmentBulkCreateIn,
    ApartmentCreateIn,
    ApartmentOut,
    BuildingCreateIn,
    BuildingOut,
    ComplexCreateIn,
    ComplexOut,
    ComplexSearchOut,
    EntranceCreateIn,
    EntranceOut,
    OrganizationCreateIn,
    OrganizationOut,
)
from app.modules.properties.service import PropertiesService

router = APIRouter(tags=["properties"])


def get_service(session: DbSession) -> PropertiesService:
    return PropertiesService(session)


ServiceDep = Annotated[PropertiesService, Depends(get_service)]


@router.get("/complexes/search", response_model=list[ComplexSearchOut], summary="Поиск ЖК")
async def search_complexes(
    service: ServiceDep,
    query: Annotated[str, Query(min_length=2, max_length=100)],
) -> list[ComplexSearchOut]:
    rows = await service.search_complexes(query)
    return [
        ComplexSearchOut(
            id=c.id, name=c.name, address=c.address, city=c.city, organization_name=org_name
        )
        for c, org_name in rows
    ]


@router.post(
    "/organizations",
    response_model=OrganizationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать организацию",
)
async def create_organization(
    payload: OrganizationCreateIn,
    service: ServiceDep,
    _: Annotated[User, Depends(require_roles(UserRoleType.PLATFORM_ADMIN))],
) -> OrganizationOut:
    organization = await service.create_organization(payload)
    return OrganizationOut.model_validate(organization)


@router.get("/organizations/{organization_id}", response_model=OrganizationOut)
async def get_organization(
    organization_id: uuid.UUID, service: ServiceDep, scope: OrganizationScope
) -> OrganizationOut:
    service.ensure_access(organization_id, scope)
    return OrganizationOut.model_validate(await service.get_organization(organization_id))


@router.get("/organizations/{organization_id}/complexes", response_model=list[ComplexOut])
async def list_complexes(
    organization_id: uuid.UUID, service: ServiceDep, scope: OrganizationScope
) -> list[ComplexOut]:
    service.ensure_access(organization_id, scope)
    return [ComplexOut.model_validate(c) for c in await service.list_complexes(organization_id)]


@router.post(
    "/organizations/{organization_id}/complexes",
    response_model=ComplexOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_complex(
    organization_id: uuid.UUID,
    payload: ComplexCreateIn,
    service: ServiceDep,
    scope: OrganizationScope,
) -> ComplexOut:
    service.ensure_access(organization_id, scope)
    return ComplexOut.model_validate(await service.create_complex(organization_id, payload))


@router.get("/complexes/{complex_id}/buildings", response_model=list[BuildingOut])
async def list_buildings(complex_id: uuid.UUID, service: ServiceDep) -> list[BuildingOut]:
    return [BuildingOut.model_validate(b) for b in await service.list_buildings(complex_id)]


@router.post(
    "/complexes/{complex_id}/buildings",
    response_model=BuildingOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_building(
    complex_id: uuid.UUID,
    payload: BuildingCreateIn,
    service: ServiceDep,
    scope: OrganizationScope,
) -> BuildingOut:
    complex_ = await service.get_complex(complex_id)
    service.ensure_access(complex_.organization_id, scope)
    return BuildingOut.model_validate(await service.create_building(complex_id, payload))


@router.get("/buildings/{building_id}/entrances", response_model=list[EntranceOut])
async def list_entrances(building_id: uuid.UUID, service: ServiceDep) -> list[EntranceOut]:
    return [EntranceOut.model_validate(e) for e in await service.list_entrances(building_id)]


@router.post(
    "/buildings/{building_id}/entrances",
    response_model=EntranceOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_entrance(
    building_id: uuid.UUID, payload: EntranceCreateIn, service: ServiceDep, _: CurrentUser
) -> EntranceOut:
    return EntranceOut.model_validate(await service.create_entrance(building_id, payload))


@router.get("/entrances/{entrance_id}/apartments", response_model=list[ApartmentOut])
async def list_apartments(entrance_id: uuid.UUID, service: ServiceDep) -> list[ApartmentOut]:
    return [ApartmentOut.model_validate(a) for a in await service.list_apartments(entrance_id)]


@router.post(
    "/entrances/{entrance_id}/apartments",
    response_model=ApartmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_apartment(
    entrance_id: uuid.UUID, payload: ApartmentCreateIn, service: ServiceDep, _: CurrentUser
) -> ApartmentOut:
    return ApartmentOut.model_validate(await service.create_apartment(entrance_id, payload))


@router.post(
    "/apartments/bulk",
    response_model=list[ApartmentOut],
    status_code=status.HTTP_201_CREATED,
    summary="Массово завести квартиры в подъезде",
)
async def bulk_create_apartments(
    payload: ApartmentBulkCreateIn, service: ServiceDep, _: CurrentUser
) -> list[ApartmentOut]:
    created = await service.bulk_create_apartments(payload)
    return [ApartmentOut.model_validate(a) for a in created]
