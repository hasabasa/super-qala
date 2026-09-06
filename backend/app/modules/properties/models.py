"""Организации и недвижимость.

Иерархия organization → complex → building → entrance → apartment
избыточна для одного дома, но без неё невозможно обслуживать
управляющую компанию с десятком домов.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
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
from app.shared.enums import OrganizationStatus, OrganizationType, Tariff


class Organization(Base, TimestampMixin):
    """ОСИ, КСК или управляющая компания. Клиент, который платит за подписку."""

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    bin: Mapped[str | None] = mapped_column(String(12), unique=True)
    type: Mapped[str] = mapped_column(String(10), default=OrganizationType.OSI, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(150))
    address: Mapped[str | None] = mapped_column(String(300))

    tariff: Mapped[str] = mapped_column(String(20), default=Tariff.BASIC, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=OrganizationStatus.TRIAL, nullable=False)
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    complexes: Mapped[list["Complex"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class Complex(Base, TimestampMixin):
    """Жилой комплекс. Может состоять из нескольких домов."""

    __tablename__ = "complexes"
    __table_args__ = (Index("ix_complexes_organization", "organization_id"),)

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str] = mapped_column(String(300), nullable=False)
    city: Mapped[str] = mapped_column(String(100), default="Астана", nullable=False)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))

    organization: Mapped[Organization] = relationship(back_populates="complexes")
    buildings: Mapped[list["Building"]] = relationship(
        back_populates="complex", cascade="all, delete-orphan"
    )


class Building(Base, TimestampMixin):
    """Дом."""

    __tablename__ = "buildings"
    __table_args__ = (
        UniqueConstraint("complex_id", "number", name="uq_building_number"),
        Index("ix_buildings_complex", "complex_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    complex_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("complexes.id", ondelete="CASCADE"), nullable=False
    )
    number: Mapped[str] = mapped_column(String(20), nullable=False)
    floors_count: Mapped[int | None] = mapped_column(Integer)

    complex: Mapped[Complex] = relationship(back_populates="buildings")
    entrances: Mapped[list["Entrance"]] = relationship(
        back_populates="building", cascade="all, delete-orphan"
    )


class Entrance(Base, TimestampMixin):
    """Подъезд."""

    __tablename__ = "entrances"
    __table_args__ = (
        UniqueConstraint("building_id", "number", name="uq_entrance_number"),
        Index("ix_entrances_building", "building_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    building_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)

    building: Mapped[Building] = relationship(back_populates="entrances")
    apartments: Mapped[list["Apartment"]] = relationship(
        back_populates="entrance", cascade="all, delete-orphan"
    )


class Apartment(Base, TimestampMixin):
    """Квартира. Площадь нужна для веса голоса на собрании собственников."""

    __tablename__ = "apartments"
    __table_args__ = (
        UniqueConstraint("entrance_id", "number", name="uq_apartment_number"),
        Index("ix_apartments_entrance", "entrance_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entrance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entrances.id", ondelete="CASCADE"), nullable=False
    )
    number: Mapped[str] = mapped_column(String(10), nullable=False)
    floor: Mapped[int | None] = mapped_column(Integer)
    area_sqm: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    rooms_count: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    entrance: Mapped[Entrance] = relationship(back_populates="apartments")
