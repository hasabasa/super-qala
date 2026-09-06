"""Доска объявлений и платное продвижение."""

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.modules.auth.models import User
from app.modules.classifieds.models import Listing, ListingPhoto, ListingPromotion
from app.modules.classifieds.schemas import ListingIn, ListingUpdateIn, PromoteIn
from app.shared.enums import ListingStatus, PromotionType

log = structlog.get_logger(__name__)

# Прайс продвижения в тенге. Само размещение бесплатно.
PROMOTION_PRICES: dict[str, int] = {
    PromotionType.PIN_TOP: 500,
    PromotionType.HIGHLIGHT: 300,
}

LISTING_TTL_DAYS = 30


class ClassifiedsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, author: User, payload: ListingIn) -> Listing:
        listing = Listing(
            complex_id=payload.complex_id,
            author_id=author.id,
            type=payload.type,
            category=payload.category,
            title=payload.title,
            description=payload.description,
            price=payload.price,
            expires_at=datetime.now(UTC) + timedelta(days=LISTING_TTL_DAYS),
        )
        self.session.add(listing)
        await self.session.flush()

        for index, photo in enumerate(payload.photos):
            self.session.add(
                ListingPhoto(listing_id=listing.id, file_url=photo.file_url, order_num=index)
            )
        await self.session.flush()
        await self.session.refresh(listing)
        return listing

    async def get(self, listing_id: uuid.UUID) -> Listing:
        listing = await self.session.get(Listing, listing_id)
        if listing is None:
            raise NotFoundError("Объявление не найдено")
        return listing

    async def list_feed(
        self,
        complex_ids: set[uuid.UUID],
        category: str | None = None,
        listing_type: str | None = None,
        query: str | None = None,
    ) -> list[tuple[Listing, User]]:
        """Лента: закреплённые сверху, остальные по свежести."""
        if not complex_ids:
            return []

        stmt = (
            select(Listing, User)
            .join(User, Listing.author_id == User.id)
            .where(
                Listing.complex_id.in_(complex_ids),
                Listing.status == ListingStatus.ACTIVE,
            )
        )
        if category:
            stmt = stmt.where(Listing.category == category)
        if listing_type:
            stmt = stmt.where(Listing.type == listing_type)
        if query:
            stmt = stmt.where(Listing.title.ilike(f"%{query.strip()}%"))

        rows = [(r[0], r[1]) for r in (await self.session.execute(stmt)).all()]
        rows.sort(key=lambda pair: (not pair[0].is_pinned, -pair[0].created_at.timestamp()))
        return rows

    async def list_mine(self, author_id: uuid.UUID) -> list[Listing]:
        result = await self.session.scalars(
            select(Listing)
            .where(Listing.author_id == author_id)
            .order_by(Listing.created_at.desc())
        )
        return list(result.all())

    async def update(
        self, listing_id: uuid.UUID, author: User, payload: ListingUpdateIn
    ) -> Listing:
        listing = await self.get(listing_id)
        if listing.author_id != author.id:
            raise PermissionDeniedError("Редактировать может только автор")
        if listing.status == ListingStatus.BLOCKED:
            raise ConflictError("Объявление заблокировано модератором")

        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(listing, field, value)
        await self.session.flush()
        return listing

    async def register_view(self, listing: Listing) -> None:
        listing.views_count += 1
        await self.session.flush()

    async def reveal_contact(self, listing_id: uuid.UUID) -> tuple[str, str]:
        """Телефон открывается по нажатию — так считается реальный интерес."""
        listing = await self.get(listing_id)
        if listing.status != ListingStatus.ACTIVE:
            raise ConflictError("Объявление неактивно")

        author = await self.session.get(User, listing.author_id)
        if author is None:
            raise NotFoundError("Автор не найден")

        listing.contacts_count += 1
        await self.session.flush()
        return author.phone, author.full_name

    async def block(self, listing_id: uuid.UUID, reason: str) -> Listing:
        listing = await self.get(listing_id)
        listing.status = ListingStatus.BLOCKED
        listing.block_reason = reason
        await self.session.flush()
        return listing

    # ------------------------------------------------------------------
    # Продвижение
    # ------------------------------------------------------------------

    async def promote(
        self, listing_id: uuid.UUID, author: User, payload: PromoteIn
    ) -> ListingPromotion:
        listing = await self.get(listing_id)
        if listing.author_id != author.id:
            raise PermissionDeniedError("Продвигать может только автор")
        if listing.status != ListingStatus.ACTIVE:
            raise ConflictError("Продвигать можно только активное объявление")

        now = datetime.now(UTC)
        promotion = ListingPromotion(
            listing_id=listing_id,
            type=payload.type,
            amount=PROMOTION_PRICES[payload.type] * payload.days // 7 or PROMOTION_PRICES[payload.type],
            days=payload.days,
            starts_at=now,
            ends_at=now + timedelta(days=payload.days),
        )
        self.session.add(promotion)
        await self.session.flush()
        return promotion

    async def confirm_promotion(
        self, promotion_id: uuid.UUID, payment_ref: str
    ) -> ListingPromotion:
        """Включает продвижение после подтверждения оплаты."""
        promotion = await self.session.get(ListingPromotion, promotion_id)
        if promotion is None:
            raise NotFoundError("Продвижение не найдено")
        if promotion.is_paid:
            raise ConflictError("Оплата уже подтверждена")

        promotion.is_paid = True
        promotion.payment_ref = payment_ref

        listing = await self.get(promotion.listing_id)
        if promotion.type == PromotionType.PIN_TOP:
            listing.pinned_until = promotion.ends_at
        else:
            listing.highlighted_until = promotion.ends_at

        await self.session.flush()
        log.info("classifieds.promoted", listing=str(listing.id), type=promotion.type)
        return promotion
