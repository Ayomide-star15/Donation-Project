import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.database import get_db
from app.core.enums import UserStatus
from app.core.security import decode_signed_token
from app.modules.auth.models import Session
from app.modules.users.models import Role, User, UserRole


bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class AuthContext:
    user: User
    session: Session


def get_auth_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: DbSession = Depends(get_db),
) -> AuthContext:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        payload = decode_signed_token(credentials.credentials, "access")
        user_id = uuid.UUID(payload["sub"])
        session_id = uuid.UUID(payload["sid"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise unauthorized

    user = db.get(User, user_id)
    session = db.get(Session, session_id)
    if (
        user is None
        or user.status != UserStatus.ACTIVE
        or session is None
        or session.user_id != user.id
        or session.revoked_at is not None
        or session.expires_at <= datetime.now(UTC)
    ):
        raise unauthorized
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
