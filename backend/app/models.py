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
    PaymentMethod,
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
from app.modules.classifieds.models import Listing, ListingPhoto, ListingPromotion
from app.modules.finance.models import BudgetItem, BudgetPeriod
from app.modules.meters.models import Meter, MeterReading
from app.modules.notifications.models import (
    Device,
    Notification,
    NotificationPreference,
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
from app.modules.voting.models import (
    Ballot,
    BallotAnswer,
    Meeting,
    MeetingQuestion,
    MeetingResult,
)

__all__ = [
    "Account",
    "Apartment",
    "ApartmentResident",
    "ApartmentVerificationCode",
    "Base",
    "Ballot",
    "BallotAnswer",
    "BillingPeriod",
    "BudgetItem",
    "BudgetPeriod",
    "Building",
    "Channel",
    "ChannelMember",
    "Device",
    "Charge",
    "Complex",
    "Entrance",
    "Invoice",
    "Listing",
    "ListingPhoto",
    "ListingPromotion",
    "Meeting",
    "MeetingQuestion",
    "MeetingResult",
    "Message",
    "MessageAttachment",
    "MessageRead",
    "Meter",
    "MeterReading",
    "Notification",
    "NotificationPreference",
    "Organization",
    "PaymentClaim",
    "PaymentFact",
    "PaymentMethod",
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
