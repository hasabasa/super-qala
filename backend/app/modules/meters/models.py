"""Приборы учёта и показания.

Распознавание с фотографии не заменяет человека: значение подставляется
в поле, а пользователь подтверждает или исправляет.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin
from app.shared.enums import ReadingSource, ReadingStatus


class Meter(Base, TimestampMixin):
    __tablename__ = "meters"
    __table_args__ = (
        UniqueConstraint("apartment_id", "type", "serial_number", name="uq_meter_serial"),
        Index("ix_meters_apartment", "apartment_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    apartment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("apartments.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    serial_number: Mapped[str | None] = mapped_column(String(50))
    installed_at: Mapped[date | None] = mapped_column(Date)
    next_check_at: Mapped[date | None] = mapped_column(
        Date, comment="Срок поверки: просрочил — начисляют по нормативу"
    )
    decimals: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="Знаков после запятой на табло"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    @property
    def check_overdue(self) -> bool:
        return self.next_check_at is not None and self.next_check_at < date.today()


class MeterReading(Base, TimestampMixin):
    __tablename__ = "meter_readings"
    __table_args__ = (
        UniqueConstraint(
            "meter_id", "period_year", "period_month", name="uq_meter_reading_period"
        ),
        Index("ix_meter_readings_meter", "meter_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meter_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("meters.id", ondelete="CASCADE"), nullable=False
    )
    value: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    previous_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    consumption: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    photo_url: Mapped[str | None] = mapped_column(String(500))
    ocr_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    ocr_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    source: Mapped[str] = mapped_column(String(15), default=ReadingSource.MANUAL, nullable=False)
    status: Mapped[str] = mapped_column(String(15), default=ReadingStatus.ACCEPTED, nullable=False)
    is_anomaly: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="Расход резко отличается от обычного"
    )
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    meter: Mapped[Meter] = relationship(lazy="joined")
