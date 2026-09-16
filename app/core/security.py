import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from cryptography.fernet import Fernet, InvalidToken
from pwdlib import PasswordHash

from app.core.config import settings


password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_hasher.verify(password, password_hash)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_token() -> str:
    return secrets.token_urlsafe(48)


def create_signed_token(
    subject: uuid.UUID,
    purpose: str,
    expires_delta: timedelta,
    **claims: Any,
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(subject),
        "purpose": purpose,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "iat": now,
        "exp": now + expires_delta,
        **claims,
    }
    return jwt.encode(
        payload,
        settings.JWT_SECRET.get_secret_value(),
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_signed_token(token: str, expected_purpose: str) -> dict[str, Any]:
    payload = jwt.decode(
        token,
        settings.JWT_SECRET.get_secret_value(),
        algorithms=[settings.JWT_ALGORITHM],
        issuer=settings.JWT_ISSUER,
        audience=settings.JWT_AUDIENCE,
    )
    if payload.get("purpose") != expected_purpose:
        raise jwt.InvalidTokenError("Unexpected token purpose")
    return payload


def create_access_token(user_id: uuid.UUID, session_id: uuid.UUID) -> str:
    return create_signed_token(
        user_id,
        "access",
        timedelta(minutes=settings.ACCESS_TOKEN_MINUTES),
        sid=str(session_id),
    )


def encrypt_mfa_secret(secret: str) -> str:
    cipher = Fernet(settings.MFA_ENCRYPTION_KEY.get_secret_value().encode("utf-8"))
    return cipher.encrypt(secret.encode("utf-8")).decode("utf-8")


def decrypt_mfa_secret(encrypted_secret: str) -> str:
    cipher = Fernet(settings.MFA_ENCRYPTION_KEY.get_secret_value().encode("utf-8"))
    try:
        return cipher.decrypt(encrypted_secret.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("Unable to decrypt MFA secret") from exc
