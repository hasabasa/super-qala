"""Эндпоинты заявок в управляющую организацию."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.deps import CurrentUser, DbSession, Scope
from app.core.exceptions import PermissionDeniedError
from app.modules.requests.schemas import (
    AssignIn,
    AttachmentOut,
    CategoryIn,
    CategoryOut,
    CommentIn,
    EventOut,
    RatingIn,
    RequestCreateIn,
    RequestDetailOut,
    RequestListOut,
    RequestOut,
    SlaReportOut,
    StatusChangeIn,
)
from app.modules.requests.service import RequestsService
from app.modules.residents.service import ResidentsService

router = APIRouter(tags=["requests"])


def get_service(session: DbSession) -> RequestsService:
    return RequestsService(session)


ServiceDep = Annotated[RequestsService, Depends(get_service)]


def _to_out(request, apartment_number: str | None = None) -> RequestOut:
    return RequestOut(
        id=request.id,
        number=request.number,
        title=request.title,
        description=request.description,
        category_name=request.category.name,
        place=request.place,
        status=request.status,
        priority=request.priority,
        sla_due_at=request.sla_due_at,
        is_overdue=request.is_overdue,
        closed_at=request.closed_at,
        rating=request.rating,
        created_at=request.created_at,
        attachments=[AttachmentOut.model_validate(a) for a in request.attachments],
    )


# ======================================================================
# Жилец
# ======================================================================


@router.get(
    "/organizations/{organization_id}/request-categories",
    response_model=list[CategoryOut],
    summary="Категории заявок",
)
async def list_categories(
    organization_id: uuid.UUID, service: ServiceDep, _: CurrentUser
) -> list[CategoryOut]:
    return [CategoryOut.model_validate(c) for c in await service.list_categories(organization_id)]


@router.post(
    "/requests",
    response_model=RequestOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать заявку",
)
async def create_request(
    payload: RequestCreateIn, user: CurrentUser, service: ServiceDep, session: DbSession
) -> RequestOut:
    residents = ResidentsService(session)
    if payload.apartment_id not in await residents.get_verified_apartment_ids(user.id):
        raise PermissionDeniedError("Квартира не подтверждена")

    organization_id = await service.resolve_organization(payload.apartment_id)
    request = await service.create(user, organization_id, payload)
    return _to_out(request)


@router.get("/requests", response_model=list[RequestListOut], summary="Мои заявки")
async def list_my_requests(
    user: CurrentUser,
    service: ServiceDep,
    only_open: Annotated[bool | None, Query()] = None,
) -> list[RequestListOut]:
    rows = await service.list_for_author(user.id, only_open)
    return [
        RequestListOut(
            id=r.id,
            number=r.number,
            title=r.title,
            category_name=r.category.name,
            status=r.status,
            priority=r.priority,
            sla_due_at=r.sla_due_at,
            is_overdue=r.is_overdue,
            created_at=r.created_at,
            apartment_number=apt,
        )
        for r, apt in rows
    ]


@router.get("/requests/{request_id}", response_model=RequestDetailOut, summary="Детали заявки")
async def get_request(
    request_id: uuid.UUID, user: CurrentUser, service: ServiceDep, scope: Scope
) -> RequestDetailOut:
    request = await service.get(request_id)
    is_staff = scope.allows(request.organization_id)
    if request.author_id != user.id and not is_staff:
        raise PermissionDeniedError("Нет доступа к этой заявке")

    events = await service.list_events(request_id, include_internal=is_staff)
    base = _to_out(request)
    return RequestDetailOut(
        **base.model_dump(),
        events=[EventOut.model_validate(e) for e in events],
        apartment_number=None,
        assigned_to=request.assigned_to,
    )


@router.post("/requests/{request_id}/rate", response_model=RequestOut, summary="Оценить заявку")
async def rate_request(
    request_id: uuid.UUID, payload: RatingIn, user: CurrentUser, service: ServiceDep
) -> RequestOut:
    request = await service.rate(request_id, user, payload.rating, payload.comment)
    return _to_out(request)


@router.post("/requests/{request_id}/comments", response_model=EventOut, summary="Комментарий")
async def add_comment(
    request_id: uuid.UUID,
    payload: CommentIn,
    user: CurrentUser,
    service: ServiceDep,
    scope: Scope,
) -> EventOut:
    request = await service.get(request_id)
    is_staff = scope.allows(request.organization_id)
    if request.author_id != user.id and not is_staff:
        raise PermissionDeniedError("Нет доступа к этой заявке")
    if payload.is_internal and not is_staff:
        raise PermissionDeniedError("Внутренние заметки доступны только сотрудникам")

    event = await service.add_comment(request_id, user, payload.comment, payload.is_internal)
    return EventOut.model_validate(event)


# ======================================================================
# Организация
# ======================================================================


@router.post(
    "/organizations/{organization_id}/request-categories",
    response_model=CategoryOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать категорию заявок",
)
async def create_category(
    organization_id: uuid.UUID, payload: CategoryIn, service: ServiceDep, scope: Scope
) -> CategoryOut:
    service.ensure_access(organization_id, scope)
    return CategoryOut.model_validate(await service.create_category(organization_id, payload))


@router.get(
    "/organizations/{organization_id}/requests",
    response_model=list[RequestListOut],
    summary="Заявки организации",
)
async def list_organization_requests(
    organization_id: uuid.UUID,
    service: ServiceDep,
    scope: Scope,
    request_status: Annotated[str | None, Query(alias="status")] = None,
    only_overdue: Annotated[bool, Query()] = False,
) -> list[RequestListOut]:
    service.ensure_access(organization_id, scope)
    rows = await service.list_for_organization(organization_id, request_status, only_overdue)
    return [
        RequestListOut(
            id=r.id,
            number=r.number,
            title=r.title,
            category_name=r.category.name,
            status=r.status,
            priority=r.priority,
            sla_due_at=r.sla_due_at,
            is_overdue=r.is_overdue,
            created_at=r.created_at,
            apartment_number=apt,
            author_name=phone,
        )
        for r, apt, phone in rows
    ]


@router.post(
    "/requests/{request_id}/status", response_model=RequestOut, summary="Сменить статус заявки"
)
async def change_status(
    request_id: uuid.UUID,
    payload: StatusChangeIn,
    user: CurrentUser,
    service: ServiceDep,
    scope: Scope,
) -> RequestOut:
    request = await service.get(request_id)
    service.ensure_access(request.organization_id, scope)
    updated = await service.change_status(request_id, payload.status, user, payload.comment)
    return _to_out(updated)


@router.post("/requests/{request_id}/assign", response_model=RequestOut, summary="Назначить")
async def assign_request(
    request_id: uuid.UUID,
    payload: AssignIn,
    user: CurrentUser,
    service: ServiceDep,
    scope: Scope,
) -> RequestOut:
    request = await service.get(request_id)
    service.ensure_access(request.organization_id, scope)
    return _to_out(await service.assign(request_id, payload.user_id, user))


@router.get(
    "/organizations/{organization_id}/requests/sla-report",
    response_model=SlaReportOut,
    summary="Отчёт по срокам выполнения",
)
async def sla_report(
    organization_id: uuid.UUID, service: ServiceDep, scope: Scope
) -> SlaReportOut:
    service.ensure_access(organization_id, scope)
    return SlaReportOut(**await service.sla_report(organization_id))
