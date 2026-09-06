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
