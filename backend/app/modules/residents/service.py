"""Привязка жильца к квартире и её подтверждение.

Три способа подтверждения, по убыванию доверия:
  1. код с бумажной квитанции  — автоматически;
  2. подтверждение администратором организации;
  3. приглашение от подтверждённого собственника — с урезанными правами.
"""

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationError
from app.modules.auth.models import User
from app.modules.properties.models import Apartment, Building, Complex, Entrance
from app.modules.residents.models import ApartmentResident, ApartmentVerificationCode
from app.modules.residents.schemas import InviteResidentIn, LinkByCodeIn, LinkRequestIn
from app.shared.enums import ResidentRelation, ResidentStatus, VerificationMethod
from app.shared.phone import normalize_phone

log = structlog.get_logger(__name__)


class ResidentsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Привязка
    # ------------------------------------------------------------------

    async def link_by_code(self, user: User, payload: LinkByCodeIn) -> ApartmentResident:
        """Код с квитанции подтверждает квартиру сразу."""
        await self._ensure_not_linked(user.id, payload.apartment_id)

        code = await self.session.scalar(
            select(ApartmentVerificationCode).where(
                ApartmentVerificationCode.apartment_id == payload.apartment_id,
                ApartmentVerificationCode.code == payload.code.strip().upper(),
            )
        )
        if code is None or not code.is_available:
            raise ValidationError("Код неверен или уже использован")

        now = datetime.now(UTC)
        code.used_by = user.id
        code.used_at = now

        resident = ApartmentResident(
            user_id=user.id,
            apartment_id=payload.apartment_id,
            relation=ResidentRelation.OWNER,
            status=ResidentStatus.VERIFIED,
            verification_method=VerificationMethod.RECEIPT_CODE,
            verified_at=now,
        )
        self.session.add(resident)
        await self.session.flush()
        log.info("residents.linked_by_code", user_id=str(user.id))
        return resident

    async def create_link_request(self, user: User, payload: LinkRequestIn) -> ApartmentResident:
        """Заявка на ручное подтверждение администратором организации."""
        await self._ensure_not_linked(user.id, payload.apartment_id)
        await self._ensure_apartment_exists(payload.apartment_id)

        resident = ApartmentResident(
            user_id=user.id,
            apartment_id=payload.apartment_id,
            relation=payload.relation,
            status=ResidentStatus.PENDING,
        )
        self.session.add(resident)
        await self.session.flush()
        log.info("residents.link_requested", user_id=str(user.id))
        return resident

    async def invite(self, owner: User, payload: InviteResidentIn) -> ApartmentResident:
        """Собственник приглашает арендатора или члена семьи.

        Приглашённый подтверждается сразу, но начислений не видит.
        """
        owner_link = await self.session.scalar(
            select(ApartmentResident).where(
                ApartmentResident.user_id == owner.id,
                ApartmentResident.apartment_id == payload.apartment_id,
                ApartmentResident.status == ResidentStatus.VERIFIED,
                ApartmentResident.relation == ResidentRelation.OWNER,
            )
        )
        if owner_link is None:
            raise PermissionDeniedError("Приглашать может только подтверждённый собственник")

        phone = normalize_phone(payload.phone)
        invitee = await self.session.scalar(select(User).where(User.phone == phone))
        if invitee is None:
            invitee = User(phone=phone)
            self.session.add(invitee)
            await self.session.flush()

        await self._ensure_not_linked(invitee.id, payload.apartment_id)

        resident = ApartmentResident(
            user_id=invitee.id,
            apartment_id=payload.apartment_id,
            relation=payload.relation,
            status=ResidentStatus.VERIFIED,
            verification_method=VerificationMethod.OWNER_INVITE,
            verified_at=datetime.now(UTC),
            invited_by=owner.id,
        )
        self.session.add(resident)
        await self.session.flush()
        return resident

    # ------------------------------------------------------------------
    # Модерация со стороны организации
    # ------------------------------------------------------------------

    async def list_pending(self, organization_id: uuid.UUID) -> list[tuple[ApartmentResident, User, Apartment, Building]]:
        rows = await self.session.execute(
            select(ApartmentResident, User, Apartment, Building)
            .join(User, ApartmentResident.user_id == User.id)
            .join(Apartment, ApartmentResident.apartment_id == Apartment.id)
            .join(Entrance, Apartment.entrance_id == Entrance.id)
            .join(Building, Entrance.building_id == Building.id)
            .join(Complex, Building.complex_id == Complex.id)
            .where(
                Complex.organization_id == organization_id,
                ApartmentResident.status == ResidentStatus.PENDING,
            )
            .order_by(ApartmentResident.created_at)
        )
        return [(r[0], r[1], r[2], r[3]) for r in rows.all()]

    async def approve(self, resident_id: uuid.UUID, admin: User) -> ApartmentResident:
        resident = await self.get_resident(resident_id)
        if resident.status != ResidentStatus.PENDING:
            raise ConflictError("Заявка уже обработана")

        resident.status = ResidentStatus.VERIFIED
        resident.verification_method = VerificationMethod.OSI_ADMIN
        resident.verified_by = admin.id
        resident.verified_at = datetime.now(UTC)
        await self.session.flush()
        log.info("residents.approved", resident_id=str(resident_id))
        return resident

    async def reject(self, resident_id: uuid.UUID, admin: User, reason: str) -> ApartmentResident:
        resident = await self.get_resident(resident_id)
        if resident.status != ResidentStatus.PENDING:
            raise ConflictError("Заявка уже обработана")

        resident.status = ResidentStatus.REJECTED
        resident.verified_by = admin.id
        resident.rejection_reason = reason
        await self.session.flush()
        return resident

    # ------------------------------------------------------------------
    # Чтение
    # ------------------------------------------------------------------

    async def list_my_apartments(
        self, user_id: uuid.UUID
    ) -> list[tuple[ApartmentResident, Complex, Building]]:
        rows = await self.session.execute(
            select(ApartmentResident, Complex, Building)
            .join(Apartment, ApartmentResident.apartment_id == Apartment.id)
            .join(Entrance, Apartment.entrance_id == Entrance.id)
            .join(Building, Entrance.building_id == Building.id)
            .join(Complex, Building.complex_id == Complex.id)
            .where(ApartmentResident.user_id == user_id)
            .order_by(ApartmentResident.created_at)
        )
        return [(r[0], r[1], r[2]) for r in rows.all()]

    async def get_verified_apartment_ids(self, user_id: uuid.UUID) -> set[uuid.UUID]:
        """Квартиры, доступ к которым подтверждён. Используется другими модулями."""
        result = await self.session.scalars(
            select(ApartmentResident.apartment_id).where(
                ApartmentResident.user_id == user_id,
                ApartmentResident.status == ResidentStatus.VERIFIED,
            )
        )
        return set(result.all())

    # ------------------------------------------------------------------
    # Внутреннее
    # ------------------------------------------------------------------

    async def get_resident(self, resident_id: uuid.UUID) -> ApartmentResident:
        resident = await self.session.get(ApartmentResident, resident_id)
        if resident is None:
            raise NotFoundError("Заявка не найдена")
        return resident

    async def _ensure_apartment_exists(self, apartment_id: uuid.UUID) -> None:
        if await self.session.get(Apartment, apartment_id) is None:
            raise NotFoundError("Квартира не найдена")

    async def _ensure_not_linked(self, user_id: uuid.UUID, apartment_id: uuid.UUID) -> None:
        existing = await self.session.scalar(
            select(ApartmentResident).where(
                ApartmentResident.user_id == user_id,
                ApartmentResident.apartment_id == apartment_id,
            )
        )
        if existing is None:
            return
        if existing.status == ResidentStatus.VERIFIED:
            raise ConflictError("Квартира уже привязана")
        if existing.status == ResidentStatus.PENDING:
            raise ConflictError("Заявка уже отправлена и ожидает подтверждения")
