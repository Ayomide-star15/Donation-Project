import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.config import settings
from app.core.security import generate_token, hash_token
from app.modules.audit.service import add_audit_log
from app.modules.invites.models import Invite
from app.modules.invites.schemas import InviteCreateRequest
from app.modules.notifications.email import EmailService
from app.modules.users.models import User

logger = logging.getLogger(__name__)

INVITE_EXPIRY_DAYS = 7
INVITE_PURPOSE = "community_admin"


def create_invite(
    db: DbSession,
    email_service: EmailService,
    payload: InviteCreateRequest,
    actor: User,
) -> Invite:
    normalized_email = payload.email.strip().lower()
    now = datetime.now(UTC)

    # Reject if there's already a pending invite for this email
    existing_pending = db.scalar(
        select(Invite).where(
            Invite.email == normalized_email,
            Invite.purpose == INVITE_PURPOSE,
            Invite.status == "pending",
        )
    )
    if existing_pending is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "A pending invite already exists for this email. "
            "Revoke it first or wait for it to expire.",
        )

    raw_token = generate_token()

    invite = Invite(
        token_hash=hash_token(raw_token),
        email=normalized_email,
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        community_name=payload.community_name.strip(),
        purpose=INVITE_PURPOSE,
        status="pending",
        invited_by=actor.id,
        expires_at=now + timedelta(days=INVITE_EXPIRY_DAYS),
    )
    db.add(invite)
    db.flush()

    invite_link = f"{settings.FRONTEND_URL.rstrip('/')}/invite/accept?token={raw_token}"

    try:
        email_service.send_community_admin_invite(
            recipient=normalized_email,
            first_name=invite.first_name,
            community_name=invite.community_name,
            inviter_name=f"{actor.first_name} {actor.last_name}".strip(),
            invite_link=invite_link,
            expires_in_days=INVITE_EXPIRY_DAYS,
        )
    except Exception as exc:
        logger.exception("INVITE EMAIL FAILED: %s", exc)
        db.rollback()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Could not send invitation email",
        )


    add_audit_log(
        db,
        "invite.created",
        actor_user_id=actor.id,
        target_type="invite",
        target_id=str(invite.id),
        details={
            "email": normalized_email,
            "community_name": invite.community_name,
        },
    )
    db.commit()
    db.refresh(invite)
    return invite


def list_invites(db: DbSession, *, limit: int = 100, offset: int = 0) -> list[Invite]:
    stmt = select(Invite).order_by(Invite.created_at.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt))


def revoke_invite(
    db: DbSession, invite_id: uuid.UUID, actor: User
) -> None:
    invite = db.get(Invite, invite_id)
    if invite is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invite not found")
    if invite.status != "pending":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Cannot revoke an invite with status '{invite.status}'",
        )
    invite.status = "revoked"
    invite.revoked_at = datetime.now(UTC)

    add_audit_log(
        db,
        "invite.revoked",
        actor_user_id=actor.id,
        target_type="invite",
        target_id=str(invite.id),
    )
    db.commit()