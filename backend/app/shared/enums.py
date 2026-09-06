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


class ResidentRelation(StrEnum):
    OWNER = "owner"
    TENANT = "tenant"
    FAMILY_MEMBER = "family_member"


class VerificationStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    REVOKED = "revoked"
