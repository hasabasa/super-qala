"""Доска объявлений.

Размещение бесплатное: платная доска не набирает объявлений, а пустая
доска мертва. Зарабатываем только на продвижении.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin
from app.shared.enums import ListingStatus, ListingType


class Listing(Base, TimestampMixin):
    __tablename__ = "listings"
    __table_args__ = (
        Index("ix_listings_complex_status", "complex_id", "status"),
        Index("ix_listings_author", "author_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    complex_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("complexes.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(15), default=ListingType.SELL, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[int | None] = mapped_column(Integer, comment="Тенге; пусто — договорная")
    status: Mapped[str] = mapped_column(String(15), default=ListingStatus.ACTIVE, nullable=False)
    views_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    contacts_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="Сколько раз открывали телефон"
    )

    pinned_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    highlighted_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    block_reason: Mapped[str | None] = mapped_column(String(300))

    photos: Mapped[list["ListingPhoto"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="ListingPhoto.order_num"
    )

    @property
    def is_pinned(self) -> bool:
        from datetime import UTC

        return self.pinned_until is not None and self.pinned_until > datetime.now(UTC)

    @property
    def is_highlighted(self) -> bool:
        from datetime import UTC

        return self.highlighted_until is not None and self.highlighted_until > datetime.now(UTC)


class ListingPhoto(Base, TimestampMixin):
    __tablename__ = "listing_photos"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    listing_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    order_num: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ListingPromotion(Base, TimestampMixin):
    """Оплаченное продвижение. Единственная монетизация доски."""

    __tablename__ = "listing_promotions"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    listing_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(15), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    days: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payment_ref: Mapped[str | None] = mapped_column(String(100))
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
