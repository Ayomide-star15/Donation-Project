"""Import all ORM models so Alembic can discover their metadata."""

from app.modules.audit.models import AuditLog
from app.modules.auth.models import OtpChallenge, Session
from app.modules.users.models import Permission, Role, RolePermission, User, UserRole

__all__ = [
    "AuditLog",
    "OtpChallenge",
    "Permission",
    "Role",
    "RolePermission",
    "Session",
    "User",
    "UserRole",
]
