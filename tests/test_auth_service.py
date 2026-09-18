import os
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as DbSession

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost/test")
os.environ.setdefault("OTP_PEPPER", "test-only-otp-pepper-with-at-least-32-characters")

import app.models  # noqa: F401
from app.core.database import Base
from app.core.enums import UserStatus
from app.core.security import hash_password
from app.modules.auth.models import Session
from app.modules.auth.service import authenticate_password, verify_email_otp
from app.modules.users.models import Role, User, UserRole


class CapturingEmailService:
    def __init__(self) -> None:
        self.recipient: str | None = None
        self.code: str | None = None

    def send_login_otp(self, recipient: str, code: str, expires_in_minutes: int) -> None:
        self.recipient = recipient
        self.code = code


@pytest.fixture
def db() -> DbSession:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with DbSession(engine, expire_on_commit=False) as session:
        yield session


def create_super_admin(db: DbSession) -> User:
    role = Role(name="super_admin", is_system=True)
    user = User(
        email="admin@example.com",
        password_hash=hash_password("a-secure-admin-password"),
        first_name="LifeLink",
        last_name="Admin",
        status=UserStatus.ACTIVE,
        email_verified_at=datetime.now(UTC),
    )
    db.add_all([role, user])
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.commit()
    return user


def test_super_admin_password_then_email_otp_creates_opaque_session(db: DbSession) -> None:
    user = create_super_admin(db)
    email = CapturingEmailService()

    result = authenticate_password(
        db,
        email,
        user.email,
        "a-secure-admin-password",
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert result.status == "otp_required"
    assert result.challenge is not None
    assert email.recipient == user.email
    assert email.code is not None
    assert email.code not in result.challenge.code_hash

    issued = verify_email_otp(
        db,
        result.challenge.id,
        email.code,
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert issued.session.auth_level == "password_otp"
    assert issued.raw_token not in issued.session.token_hash
    assert db.get(Session, issued.session.id) is not None

    with pytest.raises(HTTPException):
        verify_email_otp(
            db,
            result.challenge.id,
            email.code,
            ip_address="127.0.0.1",
            user_agent="pytest",
        )
