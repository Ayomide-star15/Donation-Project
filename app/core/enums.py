from enum import StrEnum


class UserStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    BANNED = "banned"
    DISABLED = "disabled"


class MfaMethodType(StrEnum):
    TOTP = "totp"


class AuditOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
