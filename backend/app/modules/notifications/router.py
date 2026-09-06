"""Эндпоинты уведомлений."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query, status

from app.core.deps import CurrentUser, DbSession, Scope
from app.modules.notifications.schemas import (
    BroadcastIn,
    BroadcastOut,
    DeviceIn,
    DeviceOut,
    NotificationOut,
    NotificationPage,
    PreferenceIn,
    PreferenceOut,
)
from app.modules.notifications.service import NotificationService
from app.shared.enums import NotificationType

router = APIRouter(tags=["notifications"])


def get_service(session: DbSession) -> NotificationService:
    return NotificationService(session)


ServiceDep = Annotated[NotificationService, Depends(get_service)]


@router.post(
    "/devices",
    response_model=DeviceOut,
    status_code=status.HTTP_201_CREATED,
    summary="Зарегистрировать устройство для push",
)
async def register_device(
    payload: DeviceIn, user: CurrentUser, service: ServiceDep
) -> DeviceOut:
    return DeviceOut.model_validate(await service.register_device(user.id, payload))


@router.delete(
    "/devices", status_code=status.HTTP_204_NO_CONTENT, summary="Отключить устройство"
)
async def unregister_device(
    user: CurrentUser,
    service: ServiceDep,
    fcm_token: Annotated[str, Body(embed=True)],
) -> None:
    await service.unregister_device(user.id, fcm_token)


@router.get("/notifications", response_model=NotificationPage, summary="Мои уведомления")
async def list_notifications(
    user: CurrentUser,
    service: ServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    cursor: Annotated[str | None, Query()] = None,
) -> NotificationPage:
    rows, next_cursor, unread = await service.list_for_user(user.id, limit, cursor)
    return NotificationPage(
        items=[NotificationOut.model_validate(n) for n in rows],
        unread_count=unread,
        next_cursor=next_cursor,
    )


@router.post("/notifications/read", summary="Отметить прочитанными")
async def mark_read(
    user: CurrentUser,
    service: ServiceDep,
    notification_ids: Annotated[list[uuid.UUID] | None, Body(embed=True)] = None,
) -> dict[str, int]:
    return {"marked": await service.mark_read(user.id, notification_ids)}


@router.get(
    "/notifications/preferences",
    response_model=list[PreferenceOut],
    summary="Настройки уведомлений",
)
async def list_preferences(user: CurrentUser, service: ServiceDep) -> list[PreferenceOut]:
    prefs = await service.list_preferences(user.id)
    return [PreferenceOut(type=t, push_enabled=v) for t, v in prefs.items()]


@router.put(
    "/notifications/preferences",
    response_model=PreferenceOut,
    summary="Изменить настройку уведомлений",
)
async def set_preference(
    payload: PreferenceIn, user: CurrentUser, service: ServiceDep
) -> PreferenceOut:
    preference = await service.set_preference(user.id, payload.type, payload.push_enabled)
    return PreferenceOut(type=preference.type, push_enabled=preference.push_enabled)


@router.post(
    "/organizations/{organization_id}/notifications/broadcast",
    response_model=BroadcastOut,
    summary="Рассылка жильцам ЖК",
)
async def broadcast(
    organization_id: uuid.UUID,
    payload: BroadcastIn,
    service: ServiceDep,
    session: DbSession,
    scope: Scope,
) -> BroadcastOut:
    scope.ensure(organization_id)

    from sqlalchemy import select

    from app.modules.properties.models import Apartment, Building, Complex, Entrance
    from app.modules.residents.models import ApartmentResident
    from app.shared.enums import ResidentStatus

    user_ids = list(
        (
            await session.scalars(
                select(ApartmentResident.user_id)
                .join(Apartment, ApartmentResident.apartment_id == Apartment.id)
                .join(Entrance, Apartment.entrance_id == Entrance.id)
                .join(Building, Entrance.building_id == Building.id)
                .join(Complex, Building.complex_id == Complex.id)
                .where(
                    Complex.id == payload.complex_id,
                    Complex.organization_id == organization_id,
                    ApartmentResident.status == ResidentStatus.VERIFIED,
                )
                .distinct()
            )
        ).all()
    )

    created = await service.notify_many(
        user_ids,
        NotificationType.ANNOUNCEMENT,
        payload.title,
        payload.body,
        {"type": "announcement", "complex_id": str(payload.complex_id)},
    )
    sent = await service.deliver_pending()
    return BroadcastOut(recipients=len(created), sent=sent)
