"""Эндпоинты приборов учёта."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.deps import CurrentUser, DbSession, Scope
from app.core.exceptions import PermissionDeniedError
from app.modules.meters.schemas import (
    MeterIn,
    MeterOut,
    MeterWithLastOut,
    ReadingIn,
    ReadingOut,
    ReadingsExportRow,
)
from app.modules.meters.service import MetersService
from app.modules.residents.service import ResidentsService

router = APIRouter(tags=["meters"])


def get_service(session: DbSession) -> MetersService:
    return MetersService(session)


ServiceDep = Annotated[MetersService, Depends(get_service)]


@router.get("/meters", response_model=list[MeterWithLastOut], summary="Мои счётчики")
async def list_my_meters(
    user: CurrentUser, service: ServiceDep, session: DbSession
) -> list[MeterWithLastOut]:
    apartment_ids = await ResidentsService(session).get_verified_apartment_ids(user.id)
    rows = await service.list_for_apartments(apartment_ids)

    from datetime import datetime

    now = datetime.now()
    return [
        MeterWithLastOut(
            id=meter.id,
            apartment_id=meter.apartment_id,
            type=meter.type,
            serial_number=meter.serial_number,
            next_check_at=meter.next_check_at,
            check_overdue=meter.check_overdue,
            decimals=meter.decimals,
            last_value=last.value if last else None,
            last_period=f"{last.period_month:02d}.{last.period_year}" if last else None,
            needs_reading=not (
                last and last.period_year == now.year and last.period_month == now.month
            ),
        )
        for meter, last in rows
    ]


@router.post(
    "/meters/{meter_id}/readings",
    response_model=ReadingOut,
    status_code=status.HTTP_201_CREATED,
    summary="Передать показания",
)
async def submit_reading(
    meter_id: uuid.UUID,
    payload: ReadingIn,
    user: CurrentUser,
    service: ServiceDep,
    session: DbSession,
) -> ReadingOut:
    meter = await service.get(meter_id)
    if meter.apartment_id not in await ResidentsService(session).get_verified_apartment_ids(
        user.id
    ):
        raise PermissionDeniedError("Нет доступа к этому прибору учёта")
    return ReadingOut.model_validate(await service.submit_reading(meter_id, user.id, payload))


@router.get(
    "/meters/{meter_id}/readings", response_model=list[ReadingOut], summary="История показаний"
)
async def list_readings(
    meter_id: uuid.UUID, user: CurrentUser, service: ServiceDep, session: DbSession
) -> list[ReadingOut]:
    meter = await service.get(meter_id)
    if meter.apartment_id not in await ResidentsService(session).get_verified_apartment_ids(
        user.id
    ):
        raise PermissionDeniedError("Нет доступа к этому прибору учёта")
    return [ReadingOut.model_validate(r) for r in await service.list_readings(meter_id)]


@router.post(
    "/meters",
    response_model=MeterOut,
    status_code=status.HTTP_201_CREATED,
    summary="Завести прибор учёта",
)
async def create_meter(
    payload: MeterIn, service: ServiceDep, scope: Scope, _: CurrentUser
) -> MeterOut:
    organization_id = await service.resolve_organization(payload.apartment_id)
    scope.ensure(organization_id)
    return MeterOut.model_validate(await service.create(payload))


@router.get(
    "/organizations/{organization_id}/meters/export",
    response_model=list[ReadingsExportRow],
    summary="Выгрузка показаний за месяц",
)
async def export_readings(
    organization_id: uuid.UUID,
    service: ServiceDep,
    scope: Scope,
    year: Annotated[int, Query(ge=2020, le=2100)],
    month: Annotated[int, Query(ge=1, le=12)],
) -> list[ReadingsExportRow]:
    scope.ensure(organization_id)
    return [ReadingsExportRow(**row) for row in await service.export_period(organization_id, year, month)]
