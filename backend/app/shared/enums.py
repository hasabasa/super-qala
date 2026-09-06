"""Перечисления, общие для нескольких модулей."""

from enum import StrEnum


class UserRoleType(StrEnum):
    RESIDENT = "resident"
    OSI_ADMIN = "osi_admin"
    OSI_MODERATOR = "osi_moderator"
    OSI_FINANCE = "osi_finance"
    STORE_OWNER = "store_owner"
    MASTER = "master"
    PLATFORM_ADMIN = "platform_admin"


class Language(StrEnum):
    RU = "ru"
    KK = "kk"


class OrganizationType(StrEnum):
    """Форма управляющей организации."""

    OSI = "osi"
    KSK = "ksk"
    UK = "uk"


class OrganizationStatus(StrEnum):
    TRIAL = "trial"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class Tariff(StrEnum):
    BASIC = "basic"
    STANDARD = "standard"
    PRO = "pro"


class MeterType(StrEnum):
    COLD_WATER = "cold_water"
    HOT_WATER = "hot_water"
    ELECTRICITY = "electricity"
    GAS = "gas"
    HEATING = "heating"


class ResidentRelation(StrEnum):
    """Отношение жильца к квартире."""

    OWNER = "owner"
    TENANT = "tenant"
    FAMILY_MEMBER = "family_member"


class ResidentStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    REVOKED = "revoked"


class VerificationMethod(StrEnum):
    """Каким способом подтверждена привязка к квартире."""

    RECEIPT_CODE = "receipt_code"
    OSI_ADMIN = "osi_admin"
    OWNER_INVITE = "owner_invite"


class BillingPeriodStatus(StrEnum):
    """Черновик виден только организации; опубликованный — жильцам."""

    DRAFT = "draft"
    PUBLISHED = "published"
    CLOSED = "closed"


class InvoiceStatus(StrEnum):
    ISSUED = "issued"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    OVERDUE = "overdue"


class PaymentClaimStatus(StrEnum):
    """Заявление жильца об оплате. Истина — не здесь, а в PaymentFact."""

    PENDING = "pending"
    MATCHED = "matched"
    REJECTED = "rejected"


class PaymentClaimSource(StrEnum):
    KASPI_DEEPLINK = "kaspi_deeplink"
    MANUAL_RECEIPT = "manual_receipt"
    CASH = "cash"


class PaymentFactSource(StrEnum):
    """Откуда пришёл подтверждённый платёж."""

    KASPI_REGISTRY = "kaspi_registry"
    BANK_STATEMENT = "bank_statement"
    MANUAL = "manual"


class ReconciliationAction(StrEnum):
    AUTO_MATCHED = "auto_matched"
    MANUAL_MATCHED = "manual_matched"
    UNMATCHED = "unmatched"
    CLAIM_CONFIRMED = "claim_confirmed"
    CLAIM_REJECTED = "claim_rejected"


class RequestStatus(StrEnum):
    NEW = "new"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    REJECTED = "rejected"
    CLOSED = "closed"


class RequestPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    EMERGENCY = "emergency"


class RequestPlace(StrEnum):
    """Где проблема. Влияет на то, кто её видит."""

    APARTMENT = "apartment"
    ENTRANCE = "entrance"
    BUILDING = "building"
    YARD = "yard"


class RequestEventType(StrEnum):
    CREATED = "created"
    STATUS_CHANGED = "status_changed"
    COMMENT = "comment"
    ASSIGNED = "assigned"
    RATED = "rated"


class ChannelType(StrEnum):
    """Разделение на каналы обязательно: один общий чат на 300 человек
    превращается в помойку, и люди уходят обратно в WhatsApp."""

    ANNOUNCEMENTS = "announcements"
    COMPLEX = "complex"
    BUILDING = "building"
    ENTRANCE = "entrance"
    MARKETPLACE = "marketplace"


class ChannelMemberRole(StrEnum):
    MEMBER = "member"
    MODERATOR = "moderator"


class NotificationType(StrEnum):
    """Тип уведомления. Определяет текст, приоритет и экран перехода."""

    INVOICE_ISSUED = "invoice_issued"
    PAYMENT_CONFIRMED = "payment_confirmed"
    PAYMENT_DUE_SOON = "payment_due_soon"
    REQUEST_STATUS = "request_status"
    REQUEST_COMMENT = "request_comment"
    ANNOUNCEMENT = "announcement"
    CHAT_MESSAGE = "chat_message"
    METER_REMINDER = "meter_reminder"
    APARTMENT_VERIFIED = "apartment_verified"
    VOTING_STARTED = "voting_started"


class NotificationChannel(StrEnum):
    PUSH = "push"
    SMS = "sms"
    IN_APP = "in_app"


class NotificationStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


class DevicePlatform(StrEnum):
    IOS = "ios"
    ANDROID = "android"
    WEB = "web"


class ReadingSource(StrEnum):
    MANUAL = "manual"
    OCR = "ocr"
    OSI_IMPORT = "osi_import"


class ReadingStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class MeetingType(StrEnum):
    ANNUAL = "annual"
    EXTRAORDINARY = "extraordinary"
    SURVEY = "survey"


class MeetingStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    FINISHED = "finished"
    CANCELLED = "cancelled"


class MajorityType(StrEnum):
    """Какая доля голосов нужна для принятия решения."""

    SIMPLE = "simple"
    QUALIFIED = "qualified"
    UNANIMOUS = "unanimous"


class BudgetDirection(StrEnum):
    INCOME = "income"
    EXPENSE = "expense"


class ListingType(StrEnum):
    SELL = "sell"
    BUY = "buy"
    SERVICE = "service"
    GIVE_AWAY = "give_away"


class ListingStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    SOLD = "sold"
    BLOCKED = "blocked"


class PromotionType(StrEnum):
    """Размещение бесплатное — платное убивает ликвидность доски.
    Зарабатываем только на продвижении."""

    PIN_TOP = "pin_top"
    HIGHLIGHT = "highlight"
