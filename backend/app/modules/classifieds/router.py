"""Эндпоинты доски объявлений."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.deps import CurrentUser, DbSession, Scope
from app.modules.auth.models import User
from app.modules.chat.service import ChatService
from app.modules.classifieds.schemas import (
    BlockIn,
    ContactOut,
    ListingIn,
    ListingOut,
    ListingUpdateIn,
    PhotoOut,
    PromoteIn,
    PromoteOut,
)
from app.modules.classifieds.service import PROMOTION_PRICES, ClassifiedsService
from app.modules.voting.service import VotingService

router = APIRouter(tags=["classifieds"])


def get_service(session: DbSession) -> ClassifiedsService:
    return ClassifiedsService(session)


ServiceDep = Annotated[ClassifiedsService, Depends(get_service)]


def _listing_out(listing, author: User) -> ListingOut:
    return ListingOut(
        id=listing.id,
        type=listing.type,
        category=listing.category,
        title=listing.title,
        description=listing.description,
        price=listing.price,
        status=listing.status,
        views_count=listing.views_count,
        is_pinned=listing.is_pinned,
        is_highlighted=listing.is_highlighted,
        author_name=author.full_name,
        photos=[PhotoOut.model_validate(p) for p in listing.photos],
        created_at=listing.created_at,
    )


@router.post(
    "/listings",
    response_model=ListingOut,
    status_code=status.HTTP_201_CREATED,
    summary="Разместить объявление (бесплатно)",
)
async def create_listing(
    payload: ListingIn, user: CurrentUser, service: ServiceDep
) -> ListingOut:
    return _listing_out(await service.create(user, payload), user)


@router.get("/listings", response_model=list[ListingOut], summary="Лента объявлений")
async def list_feed(
    user: CurrentUser,
    service: ServiceDep,
    session: DbSession,
    category: Annotated[str | None, Query()] = None,
    listing_type: Annotated[str | None, Query(alias="type")] = None,
    query: Annotated[str | None, Query(alias="q", max_length=100)] = None,
) -> list[ListingOut]:
    complexes, _, _ = await ChatService(session)._user_scope(user.id)  # noqa: SLF001
    rows = await service.list_feed(complexes, category, listing_type, query)
    return [_listing_out(listing, author) for listing, author in rows]


@router.get("/listings/mine", response_model=list[ListingOut], summary="Мои объявления")
async def list_mine(user: CurrentUser, service: ServiceDep) -> list[ListingOut]:
    return [_listing_out(listing, user) for listing in await service.list_mine(user.id)]


@router.get("/listings/{listing_id}", response_model=ListingOut, summary="Объявление")
async def get_listing(
    listing_id: uuid.UUID, user: CurrentUser, service: ServiceDep, session: DbSession
) -> ListingOut:
    listing = await service.get(listing_id)
    await service.register_view(listing)
    author = await session.get(User, listing.author_id)
    return _listing_out(listing, author or user)


@router.post(
    "/listings/{listing_id}/contact",
    response_model=ContactOut,
    summary="Показать телефон автора",
)
async def reveal_contact(
    listing_id: uuid.UUID, _: CurrentUser, service: ServiceDep
) -> ContactOut:
    phone, name = await service.reveal_contact(listing_id)
    return ContactOut(phone=phone, author_name=name)


@router.patch("/listings/{listing_id}", response_model=ListingOut, summary="Изменить объявление")
async def update_listing(
    listing_id: uuid.UUID, payload: ListingUpdateIn, user: CurrentUser, service: ServiceDep
) -> ListingOut:
    return _listing_out(await service.update(listing_id, user, payload), user)


@router.post(
    "/listings/{listing_id}/promote",
    response_model=PromoteOut,
    status_code=status.HTTP_201_CREATED,
    summary="Заказать продвижение",
)
async def promote(
    listing_id: uuid.UUID, payload: PromoteIn, user: CurrentUser, service: ServiceDep
) -> PromoteOut:
    promotion = await service.promote(listing_id, user, payload)
    return PromoteOut(
        id=promotion.id,
        type=promotion.type,
        amount=promotion.amount,
        days=promotion.days,
        ends_at=promotion.ends_at,
        is_paid=promotion.is_paid,
        payment_hint=f"К оплате {promotion.amount} ₸",
    )


@router.post(
    "/promotions/{promotion_id}/confirm",
    response_model=PromoteOut,
    summary="Подтвердить оплату продвижения",
)
async def confirm_promotion(
    promotion_id: uuid.UUID,
    service: ServiceDep,
    scope: Scope,
    payment_ref: Annotated[str, Query(max_length=100)],
) -> PromoteOut:
    if not scope.is_platform_admin:
        from app.core.exceptions import PermissionDeniedError

        raise PermissionDeniedError("Подтверждать оплату может администратор платформы")

    promotion = await service.confirm_promotion(promotion_id, payment_ref)
    return PromoteOut(
        id=promotion.id,
        type=promotion.type,
        amount=promotion.amount,
        days=promotion.days,
        ends_at=promotion.ends_at,
        is_paid=promotion.is_paid,
        payment_hint="Оплачено",
    )


@router.post(
    "/listings/{listing_id}/block", response_model=ListingOut, summary="Заблокировать объявление"
)
async def block_listing(
    listing_id: uuid.UUID,
    payload: BlockIn,
    service: ServiceDep,
    session: DbSession,
    scope: Scope,
) -> ListingOut:
    listing = await service.get(listing_id)
    scope.ensure(await VotingService(session).organization_of(listing.complex_id))
    blocked = await service.block(listing_id, payload.reason)
    author = await session.get(User, blocked.author_id)
    return _listing_out(blocked, author)


@router.get("/promotions/prices", summary="Прайс продвижения")
async def promotion_prices(_: CurrentUser) -> dict[str, int]:
    return dict(PROMOTION_PRICES)
