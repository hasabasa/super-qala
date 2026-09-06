"""Бизнес-логика заявок в управляющую организацию."""

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AccessScope
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.modules.auth.models import User
from app.modules.properties.models import Apartment, Building, Complex, Entrance
from app.modules.requests.models import (
    RequestAttachment,
    RequestCategory,
    RequestEvent,
    ServiceRequest,
)
from app.modules.requests.schemas import CategoryIn, RequestCreateIn
from app.shared.enums import RequestEventType, RequestStatus

log = structlog.get_logger(__name__)

# Стандартный набор категорий: создаётся при первом обращении, чтобы
# организации не пришлось заполнять справочник до первой заявки.
DEFAULT_CATEGORIES: list[tuple[str, int]] = [
    ("Авария: вода, канализация", 4),
    ("Электроснабжение", 8),
    ("Отопление", 12),
    ("Лифт", 24),
    ("Уборка подъезда", 48),
    ("Освещение мест общего пользования", 48),
    ("Двор и территория", 72),
    ("Прочее", 72),
]

OPEN_STATUSES = (RequestStatus.NEW, RequestStatus.ACCEPTED, RequestStatus.IN_PROGRESS)
FINAL_STATUSES = (RequestStatus.DONE, RequestStatus.CLOSED, RequestStatus.REJECTED)


class RequestsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Категории
    # ------------------------------------------------------------------

    async def list_categories(self, organization_id: uuid.UUID) -> list[RequestCategory]:
        result = await self.session.scalars(
            select(RequestCategory)
            .where(
                RequestCategory.organization_id == organization_id,
                RequestCategory.is_active.is_(True),
            )
            .order_by(RequestCategory.order_num, RequestCategory.name)
        )
        categories = list(result.all())
        if categories:
            return categories

        for order, (name, sla) in enumerate(DEFAULT_CATEGORIES):
            self.session.add(
                RequestCategory(
                    organization_id=organization_id, name=name, sla_hours=sla, order_num=order
                )
            )
        await self.session.flush()
        result = await self.session.scalars(
            select(RequestCategory)
            .where(RequestCategory.organization_id == organization_id)
            .order_by(RequestCategory.order_num)
        )
        return list(result.all())

    async def create_category(
        self, organization_id: uuid.UUID, payload: CategoryIn
    ) -> RequestCategory:
        exists = await self.session.scalar(
            select(RequestCategory.id).where(
                RequestCategory.organization_id == organization_id,
                RequestCategory.name == payload.name,
            )
        )
        if exists:
            raise ConflictError("Категория с таким названием уже есть")
        category = RequestCategory(organization_id=organization_id, **payload.model_dump())
        self.session.add(category)
        await self.session.flush()
        return category

    # ------------------------------------------------------------------
    # Создание и чтение заявок
    # ------------------------------------------------------------------

    async def create(
        self, author: User, organization_id: uuid.UUID, payload: RequestCreateIn
    ) -> ServiceRequest:
        category = await self.session.get(RequestCategory, payload.category_id)
        if category is None or category.organization_id != organization_id:
            raise NotFoundError("Категория не найдена")

        request = ServiceRequest(
            organization_id=organization_id,
            apartment_id=payload.apartment_id,
            author_id=author.id,
            category_id=category.id,
            title=payload.title,
            description=payload.description,
            place=payload.place,
            priority=payload.priority,
            sla_due_at=datetime.now(UTC) + timedelta(hours=category.sla_hours),
        )
        self.session.add(request)
        await self.session.flush()

        for item in payload.attachments:
            self.session.add(
                RequestAttachment(
                    request_id=request.id,
                    file_url=item.file_url,
                    file_type=item.file_type,
                    uploaded_by=author.id,
                )
            )

        self.session.add(
            RequestEvent(
                request_id=request.id,
                author_id=author.id,
                event_type=RequestEventType.CREATED,
                new_status=RequestStatus.NEW,
            )
        )
        await self.session.flush()
        await self.session.refresh(request)
        log.info("requests.created", request=str(request.id), org=str(organization_id))
        return request

    async def get(self, request_id: uuid.UUID) -> ServiceRequest:
        request = await self.session.get(ServiceRequest, request_id)
        if request is None:
            raise NotFoundError("Заявка не найдена")
        return request

    async def list_for_author(
        self, author_id: uuid.UUID, only_open: bool | None = None
    ) -> list[tuple[ServiceRequest, str | None]]:
        query = (
            select(ServiceRequest, Apartment.number)
            .outerjoin(Apartment, ServiceRequest.apartment_id == Apartment.id)
            .where(ServiceRequest.author_id == author_id)
            .order_by(ServiceRequest.created_at.desc())
        )
        if only_open is True:
            query = query.where(ServiceRequest.status.in_(OPEN_STATUSES))
        elif only_open is False:
            query = query.where(ServiceRequest.status.in_(FINAL_STATUSES))

        rows = await self.session.execute(query)
        return [(r[0], r[1]) for r in rows.all()]

    async def list_for_organization(
        self,
        organization_id: uuid.UUID,
        status: str | None = None,
        only_overdue: bool = False,
    ) -> list[tuple[ServiceRequest, str | None, str]]:
        query = (
            select(ServiceRequest, Apartment.number, User.phone)
            .outerjoin(Apartment, ServiceRequest.apartment_id == Apartment.id)
            .join(User, ServiceRequest.author_id == User.id)
            .where(ServiceRequest.organization_id == organization_id)
            .order_by(ServiceRequest.created_at.desc())
        )
        if status:
            query = query.where(ServiceRequest.status == status)
        if only_overdue:
            query = query.where(
                ServiceRequest.status.in_(OPEN_STATUSES),
                ServiceRequest.sla_due_at < datetime.now(UTC),
            )
        rows = await self.session.execute(query)
        return [(r[0], r[1], r[2]) for r in rows.all()]

    async def list_events(
        self, request_id: uuid.UUID, include_internal: bool
    ) -> list[RequestEvent]:
        query = select(RequestEvent).where(RequestEvent.request_id == request_id)
        if not include_internal:
            query = query.where(RequestEvent.is_internal.is_(False))
        result = await self.session.scalars(query.order_by(RequestEvent.created_at))
        return list(result.all())

    # ------------------------------------------------------------------
    # Изменение состояния
    # ------------------------------------------------------------------

    async def change_status(
        self, request_id: uuid.UUID, new_status: str, actor: User, comment: str | None
    ) -> ServiceRequest:
        request = await self.get(request_id)
        if request.status == new_status:
            raise ConflictError("Заявка уже в этом статусе")

        old = request.status
        request.status = new_status
        if new_status in FINAL_STATUSES:
            request.closed_at = datetime.now(UTC)

        self.session.add(
            RequestEvent(
                request_id=request.id,
                author_id=actor.id,
                event_type=RequestEventType.STATUS_CHANGED,
                old_status=old,
                new_status=new_status,
                comment=comment,
            )
        )
        await self.session.flush()

        from app.modules.notifications.service import NotificationService
        from app.shared.enums import NotificationType

        await NotificationService(self.session).notify(
            request.author_id,
            NotificationType.REQUEST_STATUS,
            f"Заявка №{request.number}",
            f"Статус изменён: {new_status}",
            {"type": "request", "id": str(request.id)},
        )

        log.info("requests.status_changed", request=str(request_id), status=new_status)
        return request

    async def add_comment(
        self, request_id: uuid.UUID, actor: User, comment: str, is_internal: bool
    ) -> RequestEvent:
        await self.get(request_id)
        event = RequestEvent(
            request_id=request_id,
            author_id=actor.id,
            event_type=RequestEventType.COMMENT,
            comment=comment,
            is_internal=is_internal,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def assign(
        self, request_id: uuid.UUID, assignee_id: uuid.UUID, actor: User
    ) -> ServiceRequest:
        request = await self.get(request_id)
        request.assigned_to = assignee_id
        if request.status == RequestStatus.NEW:
            request.status = RequestStatus.ACCEPTED
        self.session.add(
            RequestEvent(
                request_id=request.id,
                author_id=actor.id,
                event_type=RequestEventType.ASSIGNED,
                comment=str(assignee_id),
            )
        )
        await self.session.flush()
        return request

    async def rate(
        self, request_id: uuid.UUID, author: User, rating: int, comment: str | None
    ) -> ServiceRequest:
        request = await self.get(request_id)
        if request.author_id != author.id:
            raise PermissionDeniedError("Оценить заявку может только её автор")
        if request.status not in (RequestStatus.DONE, RequestStatus.CLOSED):
            raise ConflictError("Оценка доступна только после выполнения заявки")
        if request.rating is not None:
            raise ConflictError("Заявка уже оценена")

        request.rating = rating
        request.rating_comment = comment
        if request.status == RequestStatus.DONE:
            request.status = RequestStatus.CLOSED

        self.session.add(
            RequestEvent(
                request_id=request.id,
                author_id=author.id,
                event_type=RequestEventType.RATED,
                comment=comment,
            )
        )
        await self.session.flush()
        return request

    # ------------------------------------------------------------------
    # Отчётность
    # ------------------------------------------------------------------

    async def sla_report(self, organization_id: uuid.UUID) -> dict:
        """Соблюдение сроков — ключевой отчёт для организации."""
        now = datetime.now(UTC)
        row = await self.session.execute(
            select(
                func.count(ServiceRequest.id),
                func.sum(
                    case(
                        (
                            ServiceRequest.status.in_(FINAL_STATUSES)
                            & (ServiceRequest.closed_at <= ServiceRequest.sla_due_at),
                            1,
                        ),
                        else_=0,
                    )
                ),
                func.sum(
                    case(
                        (
                            ServiceRequest.status.in_(FINAL_STATUSES)
                            & (ServiceRequest.closed_at > ServiceRequest.sla_due_at),
                            1,
                        ),
                        else_=0,
                    )
                ),
                func.sum(
                    case(
                        (
                            ServiceRequest.status.in_(OPEN_STATUSES)
                            & (ServiceRequest.sla_due_at < now),
                            1,
                        ),
                        else_=0,
                    )
                ),
                func.sum(case((ServiceRequest.status.in_(OPEN_STATUSES), 1), else_=0)),
                func.avg(
                    case(
                        (
                            ServiceRequest.closed_at.isnot(None),
                            func.extract(
                                "epoch", ServiceRequest.closed_at - ServiceRequest.created_at
                            )
                            / 3600,
                        )
                    )
                ),
            ).where(ServiceRequest.organization_id == organization_id)
        )
        total, in_time, overdue, open_overdue, open_total, avg_hours = row.one()
        total = int(total or 0)
        in_time = int(in_time or 0)
        overdue = int(overdue or 0)
        closed = in_time + overdue
        return {
            "total": total,
            "closed_in_time": in_time,
            "closed_overdue": overdue,
            "open_overdue": int(open_overdue or 0),
            "open_total": int(open_total or 0),
            "sla_rate": round(in_time / closed * 100, 1) if closed else 0.0,
            "average_hours": round(float(avg_hours), 1) if avg_hours is not None else None,
        }

    # ------------------------------------------------------------------
    # Доступ
    # ------------------------------------------------------------------

    async def resolve_organization(self, apartment_id: uuid.UUID) -> uuid.UUID:
        organization_id = await self.session.scalar(
            select(Complex.organization_id)
            .join(Building, Building.complex_id == Complex.id)
            .join(Entrance, Entrance.building_id == Building.id)
            .join(Apartment, Apartment.entrance_id == Entrance.id)
            .where(Apartment.id == apartment_id)
        )
        if organization_id is None:
            raise NotFoundError("Квартира не найдена")
        return organization_id

    @staticmethod
    def ensure_access(organization_id: uuid.UUID, scope: AccessScope) -> None:
        scope.ensure(organization_id)
