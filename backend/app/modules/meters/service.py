"""Приборы учёта: ведение и приём показаний."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.meters.models import Meter, MeterReading
from app.modules.meters.schemas import MeterIn, ReadingIn
from app.modules.properties.models import Apartment, Building, Complex, Entrance
from app.shared.enums import ReadingSource, ReadingStatus

log = structlog.get_logger(__name__)

# Расход выше среднего во столько раз считается аномальным и помечается
# для проверки. Это подсказка организации, а не отказ в приёме.
ANOMALY_FACTOR = Decimal("3")


class MetersService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Приборы
    # ------------------------------------------------------------------

    async def create(self, payload: MeterIn) -> Meter:
        exists = await self.session.scalar(
            select(Meter.id).where(
                Meter.apartment_id == payload.apartment_id,
                Meter.type == payload.type,
                Meter.serial_number == payload.serial_number,
            )
        )
        if exists:
            raise ConflictError("Такой прибор уже заведён")

        meter = Meter(**payload.model_dump())
        self.session.add(meter)
        await self.session.flush()
        return meter

    async def get(self, meter_id: uuid.UUID) -> Meter:
        meter = await self.session.get(Meter, meter_id)
        if meter is None or not meter.is_active:
            raise NotFoundError("Прибор учёта не найден")
        return meter

    async def list_for_apartments(
        self, apartment_ids: set[uuid.UUID]
    ) -> list[tuple[Meter, MeterReading | None]]:
        if not apartment_ids:
            return []

        meters = list(
            (
                await self.session.scalars(
                    select(Meter)
                    .where(Meter.apartment_id.in_(apartment_ids), Meter.is_active.is_(True))
                    .order_by(Meter.type)
                )
            ).all()
        )

        result: list[tuple[Meter, MeterReading | None]] = []
        for meter in meters:
            last = await self._last_reading(meter.id)
            result.append((meter, last))
        return result

    async def _last_reading(self, meter_id: uuid.UUID) -> MeterReading | None:
        return await self.session.scalar(
            select(MeterReading)
            .where(
                MeterReading.meter_id == meter_id,
                MeterReading.status != ReadingStatus.REJECTED,
            )
            .order_by(MeterReading.period_year.desc(), MeterReading.period_month.desc())
            .limit(1)
        )

    # ------------------------------------------------------------------
    # Показания
    # ------------------------------------------------------------------

    async def submit_reading(
        self, meter_id: uuid.UUID, user_id: uuid.UUID | None, payload: ReadingIn
    ) -> MeterReading:
        meter = await self.get(meter_id)
        now = datetime.now(UTC)
        year = payload.period_year or now.year
        month = payload.period_month or now.month

        existing = await self.session.scalar(
            select(MeterReading).where(
                MeterReading.meter_id == meter_id,
                MeterReading.period_year == year,
                MeterReading.period_month == month,
            )
        )
        if existing is not None:
            raise ConflictError("Показания за этот месяц уже переданы")

        previous = await self._last_reading(meter_id)
        previous_value = previous.value if previous else None

        if previous_value is not None and payload.value < previous_value:
            raise ValidationError(
                "Показание меньше предыдущего. Проверьте значение",
                previous_value=str(previous_value),
            )

        consumption = payload.value - previous_value if previous_value is not None else None
        reading = MeterReading(
            meter_id=meter_id,
            value=payload.value,
            previous_value=previous_value,
            consumption=consumption,
            photo_url=payload.photo_url,
            ocr_value=payload.ocr_value,
            ocr_confidence=payload.ocr_confidence,
            source=ReadingSource.OCR if payload.ocr_value is not None else ReadingSource.MANUAL,
            period_year=year,
            period_month=month,
            submitted_by=user_id,
            submitted_at=now,
            is_anomaly=await self._is_anomaly(meter_id, consumption),
        )
        self.session.add(reading)
        await self.session.flush()
        log.info("meters.reading_submitted", meter=str(meter_id), anomaly=reading.is_anomaly)
        return reading

    async def _is_anomaly(self, meter_id: uuid.UUID, consumption: Decimal | None) -> bool:
        """Сравнивает расход со средним по последним месяцам."""
        if consumption is None or consumption <= 0:
            return False

        history = list(
            (
                await self.session.scalars(
                    select(MeterReading.consumption)
                    .where(
                        MeterReading.meter_id == meter_id,
                        MeterReading.consumption.isnot(None),
                        MeterReading.status == ReadingStatus.ACCEPTED,
                    )
                    .order_by(MeterReading.period_year.desc(), MeterReading.period_month.desc())
                    .limit(6)
                )
            ).all()
        )
        values = [v for v in history if v and v > 0]
        if len(values) < 2:
            return False

        average = sum(values) / len(values)
        return consumption > average * ANOMALY_FACTOR

    async def list_readings(self, meter_id: uuid.UUID, limit: int = 24) -> list[MeterReading]:
        result = await self.session.scalars(
            select(MeterReading)
            .where(MeterReading.meter_id == meter_id)
            .order_by(MeterReading.period_year.desc(), MeterReading.period_month.desc())
            .limit(limit)
        )
        return list(result.all())

    # ------------------------------------------------------------------
    # Для организации
    # ------------------------------------------------------------------

    async def export_period(
        self, organization_id: uuid.UUID, year: int, month: int
    ) -> list[dict]:
        """Выгрузка показаний за месяц для загрузки в биллинг организации."""
        rows = await self.session.execute(
            select(
                Apartment.number,
                Building.number,
                Meter.type,
                Meter.serial_number,
                MeterReading.previous_value,
                MeterReading.value,
                MeterReading.consumption,
                MeterReading.is_anomaly,
            )
            .join(Meter, MeterReading.meter_id == Meter.id)
            .join(Apartment, Meter.apartment_id == Apartment.id)
            .join(Entrance, Apartment.entrance_id == Entrance.id)
            .join(Building, Entrance.building_id == Building.id)
            .join(Complex, Building.complex_id == Complex.id)
            .where(
                Complex.organization_id == organization_id,
                MeterReading.period_year == year,
                MeterReading.period_month == month,
                MeterReading.status != ReadingStatus.REJECTED,
            )
            .order_by(Building.number, Apartment.number, Meter.type)
        )
        return [
            {
                "apartment_number": r[0],
                "building_number": r[1],
                "meter_type": r[2],
                "serial_number": r[3],
                "previous_value": r[4],
                "value": r[5],
                "consumption": r[6],
                "is_anomaly": r[7],
            }
            for r in rows.all()
        ]

    async def apartments_without_readings(
        self, organization_id: uuid.UUID, year: int, month: int
    ) -> list[uuid.UUID]:
        """Кому напомнить о передаче показаний."""
        submitted = select(MeterReading.meter_id).where(
            MeterReading.period_year == year, MeterReading.period_month == month
        )
        result = await self.session.scalars(
            select(Meter.apartment_id)
            .join(Apartment, Meter.apartment_id == Apartment.id)
            .join(Entrance, Apartment.entrance_id == Entrance.id)
            .join(Building, Entrance.building_id == Building.id)
            .join(Complex, Building.complex_id == Complex.id)
            .where(
                Complex.organization_id == organization_id,
                Meter.is_active.is_(True),
                Meter.id.notin_(submitted),
            )
            .distinct()
        )
        return list(result.all())

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
