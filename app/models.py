"""Import all ORM models so Alembic can discover their metadata."""

from app.modules.audit.models import AuditLog
from app.modules.auth.models import AuthChallenge, MfaMethod, MfaRecoveryCode, Session
from app.modules.users.models import Permission, Role, RolePermission, User, UserRole

__all__ = [
    "AuditLog",
    "AuthChallenge",
    "MfaMethod",
    "MfaRecoveryCode",
    "Permission",
    "Role",
    "RolePermission",
    "Session",
    "User",
    "UserRole",
]
