import hashlib
import hmac
import secrets
import uuid

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


def generate_otp() -> str:
    if settings.OTP_MODE == "fixed":
        # Configuration validation guarantees this exists and is six digits.
        assert settings.FIXED_OTP_CODE is not None
        return settings.FIXED_OTP_CODE
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(challenge_id: uuid.UUID, otp: str) -> str:
    message = f"{challenge_id}:{otp}".encode()
    return hmac.new(
        settings.OTP_PEPPER.get_secret_value().encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()


def verify_otp(challenge_id: uuid.UUID, otp: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_otp(challenge_id, otp), expected_hash)
