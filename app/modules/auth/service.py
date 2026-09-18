import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session as DbSession

from app.core.config import settings
from app.core.enums import AuditOutcome, UserStatus
from app.core.security import (
    generate_otp,
    generate_token,
    hash_otp,
    hash_password,
    hash_token,
    verify_otp,
    verify_password,
)
from app.modules.audit.service import add_audit_log
from app.modules.auth.models import OtpChallenge, Session
from app.modules.notifications.email import EmailDeliveryError, EmailService
from app.modules.users.models import Role, User, UserRole

MAX_FAILED_LOGINS = 5
LOCK_MINUTES = 15
_DUMMY_PASSWORD_HASH = hash_password(generate_token())


@dataclass
class IssuedSession:
    session: Session
    raw_token: str


@dataclass
class LoginResult:
    status: str
    issued_session: IssuedSession | None = None
    challenge: OtpChallenge | None = None
    masked_email: str | None = None


def mask_email(email: str) -> str:
    local, domain = email.split("@", maxsplit=1)
    visible = local[0] if local else "*"
    return f"{visible}{'*' * max(3, len(local) - 1)}@{domain}"


def _auth_error() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")


def _user_has_role(db: DbSession, user_id: uuid.UUID, role_name: str) -> bool:
    return (
        db.scalar(
            select(UserRole.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(UserRole.user_id == user_id, Role.name == role_name)
        )
        is not None
    )


def authenticate_password(
    db: DbSession,
    email_service: EmailService,
    email: str,
    password: str,
    *,
    ip_address: str | None,
    user_agent: str | None,
) -> LoginResult:
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

    if _user_has_role(db, user.id, "super_admin"):
        challenge = _begin_otp_challenge(
            db,
            email_service,
            user,
            purpose="super_admin_login",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return LoginResult(
            status="otp_required",
            challenge=challenge,
            masked_email=mask_email(user.email),
        )

    issued = _create_session(
        db,
        user,
        auth_level="password",
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return LoginResult(status="authenticated", issued_session=issued)


def _begin_otp_challenge(
    db: DbSession,
    email_service: EmailService,
    user: User,
    *,
    purpose: str,
    ip_address: str | None,
    user_agent: str | None,
) -> OtpChallenge:
    now = datetime.now(UTC)
    db.execute(
        update(OtpChallenge)
        .where(
            OtpChallenge.user_id == user.id,
            OtpChallenge.purpose == purpose,
            OtpChallenge.used_at.is_(None),
            OtpChallenge.superseded_at.is_(None),
        )
        .values(superseded_at=now)
    )

    challenge_id = uuid.uuid4()
    code = generate_otp()
    challenge = OtpChallenge(
        id=challenge_id,
        user_id=user.id,
        purpose=purpose,
        code_hash=hash_otp(challenge_id, code),
        channel="email",
        max_attempts=settings.OTP_MAX_ATTEMPTS,
        last_sent_at=now,
        expires_at=now + timedelta(minutes=settings.OTP_EXPIRY_MINUTES),
        requested_ip=ip_address,
    )
    db.add(challenge)
    try:
        email_service.send_login_otp(user.email, code, settings.OTP_EXPIRY_MINUTES)
    except EmailDeliveryError as exc:
        db.rollback()
        add_audit_log(
            db,
            "auth.email_delivery_failed",
            actor_user_id=user.id,
            outcome=AuditOutcome.FAILURE,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.commit()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Unable to send verification code",
        ) from exc

    add_audit_log(
        db,
        "auth.email_otp_sent",
        actor_user_id=user.id,
        target_type="otp_challenge",
        target_id=str(challenge.id),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.commit()
    return challenge


def verify_email_otp(
    db: DbSession,
    challenge_id: uuid.UUID,
    code: str,
    *,
    ip_address: str | None,
    user_agent: str | None,
) -> IssuedSession:
    now = datetime.now(UTC)
    challenge = db.scalar(
        select(OtpChallenge).where(OtpChallenge.id == challenge_id).with_for_update()
    )
    invalid = (
        challenge is None
        or challenge.used_at is not None
        or challenge.superseded_at is not None
        or challenge.expires_at <= now
        or challenge.failed_attempts >= challenge.max_attempts
    )
    if invalid:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "OTP is invalid or expired")

    user = db.get(User, challenge.user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "OTP is invalid or expired")

    if not verify_otp(challenge.id, code, challenge.code_hash):
        challenge.failed_attempts += 1
        add_audit_log(
            db,
            "auth.email_otp_failed",
            actor_user_id=user.id,
            outcome=AuditOutcome.FAILURE,
            target_type="otp_challenge",
            target_id=str(challenge.id),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "OTP is invalid or expired")

    challenge.used_at = now
    add_audit_log(
        db,
        "auth.email_otp_verified",
        actor_user_id=user.id,
        target_type="otp_challenge",
        target_id=str(challenge.id),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return _create_session(
        db,
        user,
        auth_level="password_otp",
        ip_address=ip_address,
        user_agent=user_agent,
    )


def resend_email_otp(
    db: DbSession,
    email_service: EmailService,
    challenge_id: uuid.UUID,
    *,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[OtpChallenge, str]:
    now = datetime.now(UTC)
    challenge = db.scalar(
        select(OtpChallenge).where(OtpChallenge.id == challenge_id).with_for_update()
    )
    if (
        challenge is None
        or challenge.used_at is not None
        or challenge.superseded_at is not None
        or challenge.resend_count >= settings.OTP_MAX_RESENDS
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "OTP cannot be resent")

    elapsed = (now - challenge.last_sent_at).total_seconds()
    if elapsed < settings.OTP_RESEND_COOLDOWN_SECONDS:
        retry_after = int(settings.OTP_RESEND_COOLDOWN_SECONDS - elapsed) + 1
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Please wait before requesting another code",
            headers={"Retry-After": str(retry_after)},
        )

    user = db.get(User, challenge.user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "OTP cannot be resent")

    code = generate_otp()
    challenge.code_hash = hash_otp(challenge.id, code)
    challenge.failed_attempts = 0
    challenge.resend_count += 1
    challenge.last_sent_at = now
    challenge.expires_at = now + timedelta(minutes=settings.OTP_EXPIRY_MINUTES)
    try:
        email_service.send_login_otp(user.email, code, settings.OTP_EXPIRY_MINUTES)
    except EmailDeliveryError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Unable to send verification code",
        ) from exc

    add_audit_log(
        db,
        "auth.email_otp_resent",
        actor_user_id=user.id,
        target_type="otp_challenge",
        target_id=str(challenge.id),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.commit()
    return challenge, mask_email(user.email)


def _create_session(
    db: DbSession,
    user: User,
    *,
    auth_level: str,
    ip_address: str | None,
    user_agent: str | None,
) -> IssuedSession:
    now = datetime.now(UTC)
    raw_token = generate_token()
    session = Session(
        user_id=user.id,
        token_hash=hash_token(raw_token),
        auth_level=auth_level,
        device_name=user_agent[:255] if user_agent else None,
        ip_address=ip_address,
        user_agent=user_agent,
        expires_at=now + timedelta(hours=settings.SESSION_HOURS),
        idle_expires_at=now + timedelta(minutes=settings.SESSION_IDLE_MINUTES),
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
        details={"auth_level": auth_level},
    )
    db.commit()
    return IssuedSession(session=session, raw_token=raw_token)


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
    db.execute(
        update(Session)
        .where(Session.user_id == user_id, Session.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC), revocation_reason=reason)
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

    now = datetime.now(UTC)
    user.password_hash = hash_password(new_password)
    user.password_changed_at = now
    db.execute(
        update(Session)
        .where(Session.user_id == user.id, Session.revoked_at.is_(None))
        .values(revoked_at=now, revocation_reason="password_changed")
    )
    add_audit_log(db, "auth.password_changed", actor_user_id=user.id)
    db.commit()
