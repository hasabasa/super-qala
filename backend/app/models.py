"""Реестр моделей.

Alembic импортирует этот модуль, чтобы увидеть все таблицы.
Добавляя новый модуль с моделями — впиши его сюда, иначе автогенерация
миграции его не заметит.
"""

from app.core.db import Base
from app.modules.billing.models import (
    Account,
    BillingPeriod,
    Charge,
    Invoice,
    PaymentClaim,
    PaymentFact,
    ReconciliationEntry,
    ServiceType,
)
from app.modules.auth.models import PhoneVerification, RefreshToken, User, UserRole
from app.modules.chat.models import (
    Channel,
    ChannelMember,
    Message,
    MessageAttachment,
    MessageRead,
)
from app.modules.properties.models import (
    Apartment,
    Building,
    Complex,
    Entrance,
    Organization,
)
from app.modules.requests.models import (
    RequestAttachment,
    RequestCategory,
    RequestEvent,
    ServiceRequest,
)
from app.modules.residents.models import ApartmentResident, ApartmentVerificationCode

__all__ = [
    "Account",
    "Apartment",
    "ApartmentResident",
    "ApartmentVerificationCode",
    "Base",
    "BillingPeriod",
    "Building",
    "Channel",
    "ChannelMember",
    "Charge",
    "Complex",
    "Entrance",
    "Invoice",
    "Message",
    "MessageAttachment",
    "MessageRead",
    "Organization",
    "PaymentClaim",
    "PaymentFact",
    "PhoneVerification",
    "ReconciliationEntry",
    "RefreshToken",
    "RequestAttachment",
    "RequestCategory",
    "RequestEvent",
    "ServiceRequest",
    "ServiceType",
    "User",
    "UserRole",
]
