from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.config import settings
from app.core.database import get_db
from app.core.enums import UserStatus
from app.core.security import hash_token
from app.modules.auth.models import Session
from app.modules.users.models import Role, User, UserRole


@dataclass
class AuthContext:
    user: User
    session: Session


def get_auth_context(
    raw_session: str | None = Cookie(default=None, alias=settings.SESSION_COOKIE_NAME),
    db: DbSession = Depends(get_db),
) -> AuthContext:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
    )
    if raw_session is None:
        raise unauthorized

    session = db.scalar(select(Session).where(Session.token_hash == hash_token(raw_session)))
    if session is None:
        raise unauthorized

    now = datetime.now(UTC)
    if (
        session.revoked_at is not None
        or session.expires_at <= now
        or (session.idle_expires_at is not None and session.idle_expires_at <= now)
    ):
        raise unauthorized

    user = db.get(User, session.user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        raise unauthorized

    if now - session.last_seen_at >= timedelta(minutes=5):
        session.last_seen_at = now
        session.idle_expires_at = now + timedelta(minutes=settings.SESSION_IDLE_MINUTES)
        db.commit()
    return AuthContext(user=user, session=session)


def require_role(role_name: str):
    def dependency(
        context: AuthContext = Depends(get_auth_context),
        db: DbSession = Depends(get_db),
    ) -> AuthContext:
        role_exists = db.scalar(
            select(UserRole.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(UserRole.user_id == context.user.id, Role.name == role_name)
        )
        if role_exists is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permission")
        return context

    return dependency


require_super_admin = require_role("super_admin")
