"""Реестр моделей.

Alembic импортирует этот модуль, чтобы увидеть все таблицы.
Добавляя новый модуль с моделями — впиши его сюда, иначе автогенерация
миграции его не заметит.
"""

from app.core.db import Base
from app.modules.auth.models import PhoneVerification, RefreshToken, User, UserRole
from app.modules.properties.models import (
    Apartment,
    Building,
    Complex,
    Entrance,
    Organization,
)
from app.modules.residents.models import ApartmentResident, ApartmentVerificationCode

__all__ = [
    "Apartment",
    "ApartmentResident",
    "ApartmentVerificationCode",
    "Base",
    "Building",
    "Complex",
    "Entrance",
    "Organization",
    "PhoneVerification",
    "RefreshToken",
    "User",
    "UserRole",
]
