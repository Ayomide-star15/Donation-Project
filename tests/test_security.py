from datetime import timedelta
from uuid import uuid4

import jwt
import pytest

from app.core.security import (
    create_signed_token,
    decode_signed_token,
    hash_password,
    hash_token,
    verify_password,
)


def test_password_is_hashed_and_verifiable() -> None:
    password = "a-long-development-password"
    password_hash = hash_password(password)

    assert password not in password_hash
    assert verify_password(password, password_hash)
    assert not verify_password("incorrect-password", password_hash)


def test_token_hash_is_deterministic_without_exposing_token() -> None:
    token = "private-refresh-token"

    assert hash_token(token) == hash_token(token)
    assert hash_token(token) != token


def test_signed_token_enforces_purpose() -> None:
    token = create_signed_token(uuid4(), "access", timedelta(minutes=1))

    assert decode_signed_token(token, "access")["purpose"] == "access"
    with pytest.raises(jwt.InvalidTokenError):
        decode_signed_token(token, "mfa_verify")
