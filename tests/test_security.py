import os
from uuid import uuid4

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost/test")
os.environ.setdefault("OTP_PEPPER", "test-only-otp-pepper-with-at-least-32-characters")

from app.core.security import (
    generate_otp,
    hash_otp,
    hash_password,
    hash_token,
    verify_otp,
    verify_password,
)


def test_password_is_hashed_and_verifiable() -> None:
    password = "a-long-development-password"
    password_hash = hash_password(password)

    assert password not in password_hash
    assert verify_password(password, password_hash)
    assert not verify_password("incorrect-password", password_hash)


def test_session_token_hash_is_deterministic_without_exposing_token() -> None:
    token = "private-session-token"

    assert hash_token(token) == hash_token(token)
    assert hash_token(token) != token


def test_otp_is_six_digits_and_uses_keyed_verification() -> None:
    challenge_id = uuid4()
    code = generate_otp()
    code_hash = hash_otp(challenge_id, code)

    assert len(code) == 6
    assert code.isdigit()
    assert code not in code_hash
    assert verify_otp(challenge_id, code, code_hash)
    assert not verify_otp(challenge_id, "000000" if code != "000000" else "111111", code_hash)


def test_fixed_otp_mode(monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "OTP_MODE", "fixed")
    monkeypatch.setattr(settings, "FIXED_OTP_CODE", "123456")

    assert generate_otp() == "123456"


def test_fixed_otp_is_rejected_in_production() -> None:
    from app.core.config import Settings

    with pytest.raises(ValueError, match="Fixed OTP mode is forbidden"):
        Settings(
            DATABASE_URL="postgresql+psycopg://test:test@localhost/test",
            OTP_PEPPER="test-only-otp-pepper-with-at-least-32-characters",
            OTP_MODE="fixed",
            FIXED_OTP_CODE="123456",
            ENVIRONMENT="production",
            COOKIE_SECURE=True,
            EMAIL_BACKEND="smtp",
        )


def test_render_postgres_url_uses_psycopg3() -> None:
    from app.core.config import Settings

    configured = Settings(
        DATABASE_URL="postgresql://user:password@database.internal/lifelink",
        OTP_PEPPER="test-only-otp-pepper-with-at-least-32-characters",
    )

    assert configured.DATABASE_URL.startswith("postgresql+psycopg://")
