"""Бизнес-логика по организациям и недвижимости."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.modules.properties.models import (
    Apartment,
    Building,
    Complex,
    Entrance,
    Organization,
)
from app.modules.properties.schemas import (
    ApartmentBulkCreateIn,
    ApartmentCreateIn,
    BuildingCreateIn,
    ComplexCreateIn,
    EntranceCreateIn,
    OrganizationCreateIn,
)


class PropertiesService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Организации
    # ------------------------------------------------------------------

    async def create_organization(self, payload: OrganizationCreateIn) -> Organization:
        if payload.bin:
            exists = await self.session.scalar(
                select(Organization.id).where(Organization.bin == payload.bin)
            )
            if exists:
                raise ConflictError("Организация с таким БИН уже зарегистрирована")

        organization = Organization(**payload.model_dump())
        self.session.add(organization)
        await self.session.flush()
        return organization

    async def get_organization(self, organization_id: uuid.UUID) -> Organization:
        organization = await self.session.get(Organization, organization_id)
        if organization is None:
            raise NotFoundError("Организация не найдена")
        return organization

    def ensure_access(self, organization_id: uuid.UUID, scope: set[uuid.UUID]) -> None:
        """Проверяет, что пользователь вправе работать с этой организацией."""
        if organization_id not in scope:
            raise PermissionDeniedError("Нет доступа к этой организации")

    # ------------------------------------------------------------------
    # Жилые комплексы и дома
    # ------------------------------------------------------------------

    async def search_complexes(self, query: str, limit: int = 20) -> list[tuple[Complex, str]]:
        """Поиск ЖК по названию или адресу — для экрана привязки квартиры."""
        pattern = f"%{query.strip()}%"
        rows = await self.session.execute(
            select(Complex, Organization.name)
            .join(Organization, Complex.organization_id == Organization.id)
            .where(Complex.name.ilike(pattern) | Complex.address.ilike(pattern))
            .order_by(Complex.name)
            .limit(limit)
        )
        return [(row[0], row[1]) for row in rows.all()]

    async def create_complex(
        self, organization_id: uuid.UUID, payload: ComplexCreateIn
    ) -> Complex:
        await self.get_organization(organization_id)
        complex_ = Complex(organization_id=organization_id, **payload.model_dump())
        self.session.add(complex_)
        await self.session.flush()
        return complex_

    async def list_complexes(self, organization_id: uuid.UUID) -> list[Complex]:
        result = await self.session.scalars(
            select(Complex).where(Complex.organization_id == organization_id).order_by(Complex.name)
        )
        return list(result.all())

    async def get_complex(self, complex_id: uuid.UUID) -> Complex:
        complex_ = await self.session.get(Complex, complex_id)
        if complex_ is None:
            raise NotFoundError("Жилой комплекс не найден")
        return complex_

    async def create_building(
        self, complex_id: uuid.UUID, payload: BuildingCreateIn
    ) -> Building:
        await self.get_complex(complex_id)
        building = Building(complex_id=complex_id, **payload.model_dump())
        self.session.add(building)
        await self.session.flush()
        return building

    async def list_buildings(self, complex_id: uuid.UUID) -> list[Building]:
        result = await self.session.scalars(
            select(Building).where(Building.complex_id == complex_id).order_by(Building.number)
        )
        return list(result.all())

    async def create_entrance(
        self, building_id: uuid.UUID, payload: EntranceCreateIn
    ) -> Entrance:
        building = await self.session.get(Building, building_id)
        if building is None:
            raise NotFoundError("Дом не найден")
        entrance = Entrance(building_id=building_id, number=payload.number)
        self.session.add(entrance)
        await self.session.flush()
        return entrance

    async def list_entrances(self, building_id: uuid.UUID) -> list[Entrance]:
        result = await self.session.scalars(
            select(Entrance).where(Entrance.building_id == building_id).order_by(Entrance.number)
        )
        return list(result.all())

    # ------------------------------------------------------------------
    # Квартиры
    # ------------------------------------------------------------------

    async def create_apartment(
        self, entrance_id: uuid.UUID, payload: ApartmentCreateIn
    ) -> Apartment:
        entrance = await self.session.get(Entrance, entrance_id)
        if entrance is None:
            raise NotFoundError("Подъезд не найден")

        exists = await self.session.scalar(
            select(Apartment.id).where(
                Apartment.entrance_id == entrance_id, Apartment.number == payload.number
            )
        )
        if exists:
            raise ConflictError(f"Квартира {payload.number} в этом подъезде уже заведена")

        apartment = Apartment(entrance_id=entrance_id, **payload.model_dump())
        self.session.add(apartment)
        await self.session.flush()
        return apartment

    async def bulk_create_apartments(self, payload: ApartmentBulkCreateIn) -> list[Apartment]:
        """Заводит подряд идущие квартиры и расставляет этажи."""
        entrance = await self.session.get(Entrance, payload.entrance_id)
        if entrance is None:
            raise NotFoundError("Подъезд не найден")

        existing = set(
            (
                await self.session.scalars(
                    select(Apartment.number).where(Apartment.entrance_id == payload.entrance_id)
                )
            ).all()
        )

        created: list[Apartment] = []
        for index in range(payload.count):
            number = str(payload.start_number + index)
            if number in existing:
                continue
            apartment = Apartment(
                entrance_id=payload.entrance_id,
                number=number,
                floor=payload.first_floor + index // payload.apartments_per_floor,
            )
            self.session.add(apartment)
            created.append(apartment)

        await self.session.flush()
        return created

    async def list_apartments(self, entrance_id: uuid.UUID) -> list[Apartment]:
        result = await self.session.scalars(
            select(Apartment)
            .where(Apartment.entrance_id == entrance_id, Apartment.is_active.is_(True))
            .order_by(func.length(Apartment.number), Apartment.number)
        )
        return list(result.all())

    async def get_apartment(self, apartment_id: uuid.UUID) -> Apartment:
        apartment = await self.session.get(Apartment, apartment_id)
        if apartment is None:
            raise NotFoundError("Квартира не найдена")
        return apartment

    async def get_apartment_organization(self, apartment_id: uuid.UUID) -> uuid.UUID:
        """Организация, обслуживающая квартиру. Нужна для проверки прав."""
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
