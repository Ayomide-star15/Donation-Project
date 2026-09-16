import hmac
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
import pyotp
from fastapi import HTTPException, status
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session as DbSession

from app.core.config import settings
from app.core.enums import AuditOutcome, MfaMethodType, UserStatus
from app.core.security import (
    create_access_token,
    create_signed_token,
    decode_signed_token,
    decrypt_mfa_secret,
    encrypt_mfa_secret,
    generate_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.modules.audit.service import add_audit_log
from app.modules.auth.models import AuthChallenge, MfaMethod, MfaRecoveryCode, Session
from app.modules.users.models import User


MAX_FAILED_LOGINS = 5
LOCK_MINUTES = 15
RECOVERY_CODE_COUNT = 10
_DUMMY_PASSWORD_HASH = hash_password(generate_token())


@dataclass
class IssuedSession:
    access_token: str
    refresh_token: str
    recovery_codes: list[str] | None = None


def _auth_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password",
        headers={"WWW-Authenticate": "Bearer"},
    )


def authenticate_password(
    db: DbSession,
    email: str,
    password: str,
    *,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[User, str, str]:
    normalized_email = email.strip().lower()
    user = db.scalar(select(User).where(User.email == normalized_email))
    now = datetime.now(UTC)

    if user is None or user.password_hash is None:
        verify_password(password, _DUMMY_PASSWORD_HASH)
        add_audit_log(
            db,
            "auth.login_failed",
            outcome=AuditOutcome.FAILURE,
            details={"email": normalized_email, "reason": "invalid_credentials"},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.commit()
        raise _auth_error()

    if user.locked_until and user.locked_until > now:
        add_audit_log(
            db,
            "auth.login_failed",
            actor_user_id=user.id,
            outcome=AuditOutcome.FAILURE,
            details={"reason": "temporarily_locked"},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.commit()
        raise _auth_error()

    if not verify_password(password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= MAX_FAILED_LOGINS:
            user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
            user.failed_login_attempts = 0
        add_audit_log(
            db,
            "auth.login_failed",
            actor_user_id=user.id,
            outcome=AuditOutcome.FAILURE,
            details={"reason": "invalid_credentials"},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.commit()
        raise _auth_error()

    if user.status != UserStatus.ACTIVE:
        add_audit_log(
            db,
            "auth.login_failed",
            actor_user_id=user.id,
            outcome=AuditOutcome.FAILURE,
            details={"reason": "account_unavailable"},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.commit()
        raise _auth_error()

    user.failed_login_attempts = 0
    user.locked_until = None
    mfa = db.scalar(
        select(MfaMethod).where(
            MfaMethod.user_id == user.id,
            MfaMethod.method == MfaMethodType.TOTP,
            MfaMethod.disabled_at.is_(None),
        )
    )
    purpose = "mfa_verify" if mfa and mfa.verified_at else "mfa_setup"
    challenge_record = AuthChallenge(
        user_id=user.id,
        purpose=purpose,
        expires_at=now + timedelta(minutes=settings.MFA_CHALLENGE_MINUTES),
    )
    db.add(challenge_record)
    db.flush()
    challenge = create_signed_token(
        user.id,
        purpose,
        timedelta(minutes=settings.MFA_CHALLENGE_MINUTES),
        jti=str(challenge_record.id),
    )
    db.commit()
    return user, purpose, challenge


def begin_mfa_setup(db: DbSession, challenge_token: str) -> str:
    try:
        payload = decode_signed_token(challenge_token, "mfa_setup")
        user_id = uuid.UUID(payload["sub"])
        challenge_id = uuid.UUID(payload["jti"])
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired challenge") from exc

    user = db.get(User, user_id)
    challenge = db.get(AuthChallenge, challenge_id)
    if (
        user is None
        or user.status != UserStatus.ACTIVE
        or challenge is None
        or challenge.user_id != user.id
        or challenge.purpose != "mfa_setup"
        or challenge.used_at is not None
        or challenge.expires_at <= datetime.now(UTC)
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired challenge")

    secret = pyotp.random_base32()
    method = db.scalar(
        select(MfaMethod).where(
            MfaMethod.user_id == user.id,
            MfaMethod.method == MfaMethodType.TOTP,
        )
    )
    if method is None:
        method = MfaMethod(user_id=user.id, method=MfaMethodType.TOTP, encrypted_secret="")
        db.add(method)
    elif method.verified_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "MFA is already configured")
    method.encrypted_secret = encrypt_mfa_secret(secret)
    method.verified_at = None
    method.disabled_at = None
    db.commit()
    return pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name="LifeLink")


def verify_mfa_and_create_session(
    db: DbSession,
    challenge_token: str,
    code: str,
    *,
    ip_address: str | None,
    user_agent: str | None,
) -> IssuedSession:
    try:
        unverified = jwt.decode(
            challenge_token,
            settings.JWT_SECRET.get_secret_value(),
            algorithms=[settings.JWT_ALGORITHM],
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE,
        )
        purpose = unverified.get("purpose")
        if purpose not in {"mfa_setup", "mfa_verify"}:
            raise jwt.InvalidTokenError("Unexpected token purpose")
        user_id = uuid.UUID(unverified["sub"])
        challenge_id = uuid.UUID(unverified["jti"])
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired challenge") from exc

    user = db.get(User, user_id)
    challenge = db.get(AuthChallenge, challenge_id)
    method = db.scalar(
        select(MfaMethod).where(
            MfaMethod.user_id == user_id,
            MfaMethod.method == MfaMethodType.TOTP,
            MfaMethod.disabled_at.is_(None),
        )
    )
    if (
        user is None
        or user.status != UserStatus.ACTIVE
        or method is None
        or challenge is None
        or challenge.user_id != user.id
        or challenge.purpose != purpose
        or challenge.used_at is not None
        or challenge.expires_at <= datetime.now(UTC)
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired challenge")

    secret = decrypt_mfa_secret(method.encrypted_secret)
    if not pyotp.TOTP(secret).verify(code, valid_window=1):
        challenge.failed_attempts += 1
        if challenge.failed_attempts >= 5:
            challenge.used_at = datetime.now(UTC)
        add_audit_log(
            db,
            "auth.mfa_failed",
            actor_user_id=user.id,
            outcome=AuditOutcome.FAILURE,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid authentication code")

    challenge.used_at = datetime.now(UTC)
    recovery_codes = None
    if purpose == "mfa_setup":
        method.verified_at = datetime.now(UTC)
        db.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user.id))
        recovery_codes = [generate_token()[:12] for _ in range(RECOVERY_CODE_COUNT)]
        db.add_all(
            [MfaRecoveryCode(user_id=user.id, code_hash=hash_token(code)) for code in recovery_codes]
        )
        add_audit_log(db, "auth.mfa_enabled", actor_user_id=user.id)
    elif method.verified_at is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "MFA setup is incomplete")

    return _create_session(
        db,
        user,
        ip_address=ip_address,
        user_agent=user_agent,
        recovery_codes=recovery_codes,
    )


def use_recovery_code_and_create_session(
    db: DbSession,
    challenge_token: str,
    recovery_code: str,
    *,
    ip_address: str | None,
    user_agent: str | None,
) -> IssuedSession:
    try:
        payload = decode_signed_token(challenge_token, "mfa_verify")
        user_id = uuid.UUID(payload["sub"])
        challenge_id = uuid.UUID(payload["jti"])
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired challenge") from exc

    now = datetime.now(UTC)
    user = db.get(User, user_id)
    challenge = db.get(AuthChallenge, challenge_id)
    recovery = db.scalar(
        select(MfaRecoveryCode).where(
            MfaRecoveryCode.user_id == user_id,
            MfaRecoveryCode.code_hash == hash_token(recovery_code),
            MfaRecoveryCode.used_at.is_(None),
        )
    )
    if (
        user is None
        or user.status != UserStatus.ACTIVE
        or challenge is None
        or challenge.user_id != user.id
        or challenge.purpose != "mfa_verify"
        or challenge.used_at is not None
        or challenge.expires_at <= now
        or recovery is None
    ):
        add_audit_log(
            db,
            "auth.mfa_recovery_failed",
            actor_user_id=user_id if user else None,
            outcome=AuditOutcome.FAILURE,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid recovery code")

    challenge.used_at = now
    recovery.used_at = now
    add_audit_log(
        db,
        "auth.mfa_recovery_used",
        actor_user_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return _create_session(
        db,
        user,
        ip_address=ip_address,
        user_agent=user_agent,
    )


def _create_session(
    db: DbSession,
    user: User,
    *,
    ip_address: str | None,
    user_agent: str | None,
    recovery_codes: list[str] | None = None,
) -> IssuedSession:
    now = datetime.now(UTC)
    secret = generate_token()
    session = Session(
        user_id=user.id,
        refresh_token_hash=hash_token(secret),
        ip_address=ip_address,
        user_agent=user_agent,
        expires_at=now + timedelta(days=settings.REFRESH_TOKEN_DAYS),
    )
    db.add(session)
    db.flush()
    user.last_login_at = now
    add_audit_log(
        db,
        "auth.login_succeeded",
        actor_user_id=user.id,
        target_type="session",
        target_id=str(session.id),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.commit()
    return IssuedSession(
        access_token=create_access_token(user.id, session.id),
        refresh_token=f"{session.id}.{secret}",
        recovery_codes=recovery_codes,
    )


def rotate_refresh_token(db: DbSession, raw_token: str) -> IssuedSession:
    try:
        session_id_text, secret = raw_token.split(".", maxsplit=1)
        session_id = uuid.UUID(session_id_text)
    except (ValueError, AttributeError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token") from exc

    session = db.get(Session, session_id)
    now = datetime.now(UTC)
    if (
        session is None
        or session.revoked_at is not None
        or session.expires_at <= now
        or not hmac.compare_digest(session.refresh_token_hash, hash_token(secret))
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")

    user = db.get(User, session.user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")

    new_secret = generate_token()
    session.refresh_token_hash = hash_token(new_secret)
    session.last_used_at = now
    db.commit()
    return IssuedSession(
        access_token=create_access_token(user.id, session.id),
        refresh_token=f"{session.id}.{new_secret}",
    )


def revoke_session(db: DbSession, session: Session, reason: str) -> None:
    if session.revoked_at is None:
        session.revoked_at = datetime.now(UTC)
        session.revocation_reason = reason
        add_audit_log(
            db,
            "auth.session_revoked",
            actor_user_id=session.user_id,
            target_type="session",
            target_id=str(session.id),
            details={"reason": reason},
        )
        db.commit()


def revoke_all_sessions(db: DbSession, user_id: uuid.UUID, reason: str) -> None:
    now = datetime.now(UTC)
    db.execute(
        update(Session)
        .where(Session.user_id == user_id, Session.revoked_at.is_(None))
        .values(revoked_at=now, revocation_reason=reason)
    )
    add_audit_log(
        db,
        "auth.all_sessions_revoked",
        actor_user_id=user_id,
        details={"reason": reason},
    )
    db.commit()


def change_password(
    db: DbSession,
    user: User,
    current_password: str,
    new_password: str,
) -> None:
    if user.password_hash is None or not verify_password(current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    if verify_password(new_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "New password must be different")

    user.password_hash = hash_password(new_password)
    user.password_changed_at = datetime.now(UTC)
    db.execute(
        update(Session)
        .where(Session.user_id == user.id, Session.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC), revocation_reason="password_changed")
    )
    add_audit_log(
        db,
        "auth.all_sessions_revoked",
        actor_user_id=user.id,
        details={"reason": "password_changed"},
    )
    add_audit_log(db, "auth.password_changed", actor_user_id=user.id)
    db.commit()
