import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.core.config import settings
from app.core.enums import UserStatus
from app.core.security import generate_token, hash_password, hash_token
from app.modules.audit.service import add_audit_log
from app.modules.communities.models import (
    Community,
    CommunityAdmin,
    CommunityJoinLink,
    CommunityMember,
)
from app.modules.invites.models import Invite
from app.modules.notifications.email import EmailService
from app.modules.users.models import User


logger = logging.getLogger(__name__)

MEMBER_INVITE_EXPIRY_DAYS = 7
INVITE_PURPOSE_MEMBER = "community_member"


# =========================================================
# Helper
# =========================================================

def _require_community_admin(db: DbSession, user: User) -> CommunityAdmin:
    admin_link = db.scalar(
        select(CommunityAdmin).where(
            CommunityAdmin.user_id == user.id,
            CommunityAdmin.status == "active",
        )
    )
    if admin_link is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "You are not a Community Admin for any community",
        )
    return admin_link


# =========================================================
# GET /community/me
# =========================================================
def get_my_community(db: DbSession, user: User) -> dict:
    admin_link = _require_community_admin(db, user)
    community = db.get(Community, admin_link.community_id)
    if community is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Community not found")

    member_count = db.scalar(
        select(func.count(CommunityMember.id)).where(
            CommunityMember.community_id == community.id,
            CommunityMember.status == "approved",
        )
    ) or 0

    pending_count = db.scalar(
        select(func.count(CommunityMember.id)).where(
            CommunityMember.community_id == community.id,
            CommunityMember.status == "pending",
        )
    ) or 0

    return {
        "id": community.id,
        "name": community.name,
        "type": community.type,
        "state_id": community.state_id,
        "lga_id": community.lga_id,
        "state_name": community.state.name,
        "lga_name": community.lga.name,
        "status": community.status,
        "member_count": member_count,
        "pending_count": pending_count,
        "created_at": community.created_at,
    }

# =========================================================
# POST /community/members/invite
# =========================================================

def invite_member(
    db: DbSession,
    email_service: EmailService,
    actor: User,
    full_name: str,
    email: str,
) -> CommunityMember:
    admin_link = _require_community_admin(db, actor)
    community = db.get(Community, admin_link.community_id)
    if community is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Community not found")

    normalized_email = email.strip().lower()

    existing = db.scalar(
        select(CommunityMember).where(
            CommunityMember.community_id == community.id,
            CommunityMember.email == normalized_email,
        )
    )
    if existing is not None:
        if existing.status == "approved":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "This person is already a member of your community",
            )
        if existing.status == "pending":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "An invite is already pending for this email",
            )

    now = datetime.now(UTC)

    member = CommunityMember(
        community_id=community.id,
        full_name=full_name.strip(),
        email=normalized_email,
        method="invite_email",
        status="pending",
        invited_by=actor.id,
    )
    db.add(member)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This email already has a pending request for this community",
        )

    parts = full_name.strip().split()
    first_name = parts[0] if parts else "Member"
    last_name = " ".join(parts[1:]) if len(parts) > 1 else ""

    raw_token = generate_token()
    invite = Invite(
        token_hash=hash_token(raw_token),
        email=normalized_email,
        first_name=first_name,
        last_name=last_name,
        community_name=community.name,
        community_id=community.id,
        purpose=INVITE_PURPOSE_MEMBER,
        status="pending",
        invited_by=actor.id,
        expires_at=now + timedelta(days=MEMBER_INVITE_EXPIRY_DAYS),
    )
    db.add(invite)
    db.flush()

    invite_link = (
        f"{settings.FRONTEND_URL.rstrip('/')}/member-invite/accept?token={raw_token}"
    )

    try:
        email_service.send_member_invite(
            recipient=normalized_email,
            full_name=full_name,
            community_name=community.name,
            inviter_name=f"{actor.first_name} {actor.last_name}".strip(),
            invite_link=invite_link,
            expires_in_days=MEMBER_INVITE_EXPIRY_DAYS,
        )
    except Exception as exc:
        logger.exception("MEMBER INVITE EMAIL FAILED: %s", exc)
        db.rollback()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Could not send invite email",
        )

    add_audit_log(
        db,
        "community.member_invited",
        actor_user_id=actor.id,
        target_type="community_member",
        target_id=str(member.id),
        details={"email": normalized_email, "community_id": str(community.id)},
    )
    db.commit()
    db.refresh(member)
    return member


# =========================================================
# GET /community/members
# =========================================================

def list_members(
    db: DbSession,
    actor: User,
    *,
    status_filter: str | None = None,
    method_filter: str | None = None,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    admin_link = _require_community_admin(db, actor)

    stmt = select(CommunityMember).where(
        CommunityMember.community_id == admin_link.community_id
    )
    count_stmt = select(func.count(CommunityMember.id)).where(
        CommunityMember.community_id == admin_link.community_id
    )

    if status_filter:
        stmt = stmt.where(CommunityMember.status == status_filter)
        count_stmt = count_stmt.where(CommunityMember.status == status_filter)
    if method_filter:
        stmt = stmt.where(CommunityMember.method == method_filter)
        count_stmt = count_stmt.where(CommunityMember.method == method_filter)
    if search:
        like = f"%{search.lower()}%"
        cond = (
            func.lower(CommunityMember.full_name).like(like)
            | func.lower(CommunityMember.email).like(like)
        )
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)

    stmt = stmt.order_by(CommunityMember.created_at.desc()).limit(limit).offset(offset)
    rows = list(db.scalars(stmt))
    total = db.scalar(count_stmt) or 0

    return {"members": rows, "total": total, "limit": limit, "offset": offset}


# =========================================================
# GET /community/members/{id}
# =========================================================

def get_member(db: DbSession, actor: User, member_id: uuid.UUID) -> CommunityMember:
    admin_link = _require_community_admin(db, actor)
    member = db.get(CommunityMember, member_id)
    if member is None or member.community_id != admin_link.community_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    return member


# =========================================================
# DELETE /community/members/{id}
# =========================================================

def revoke_member(db: DbSession, actor: User, member_id: uuid.UUID) -> None:
    admin_link = _require_community_admin(db, actor)
    member = db.get(CommunityMember, member_id)
    if member is None or member.community_id != admin_link.community_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    if member.status != "pending":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Cannot revoke a member with status '{member.status}'",
        )

    now = datetime.now(UTC)

    invites = db.scalars(
        select(Invite).where(
            Invite.community_id == admin_link.community_id,
            Invite.email == member.email,
            Invite.status == "pending",
        )
    ).all()
    for inv in invites:
        inv.status = "revoked"
        inv.revoked_at = now

    member.status = "rejected"
    member.reviewed_by = actor.id
    member.reviewed_at = now

    add_audit_log(
        db,
        "community.member_revoked",
        actor_user_id=actor.id,
        target_type="community_member",
        target_id=str(member.id),
    )
    db.commit()


# =========================================================
# POST /community/members/{id}/approve
# =========================================================

def approve_member(db: DbSession, actor: User, member_id: uuid.UUID) -> CommunityMember:
    admin_link = _require_community_admin(db, actor)
    member = db.get(CommunityMember, member_id)
    if member is None or member.community_id != admin_link.community_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    if member.status != "pending":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Cannot approve a member with status '{member.status}'",
        )
    if member.method != "open_link":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Only open-link applications need approval. Invitees activate themselves.",
        )

    now = datetime.now(UTC)

    user = db.get(User, member.user_id) if member.user_id else None
    if user is None:
        user = db.scalar(select(User).where(User.email == member.email))
        if user is None:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "User record missing for this application",
            )
        member.user_id = user.id

    if user.status == UserStatus.PENDING:
        user.status = UserStatus.ACTIVE

    member.status = "approved"
    member.reviewed_by = actor.id
    member.reviewed_at = now
    member.joined_at = now

    add_audit_log(
        db,
        "community.member_approved",
        actor_user_id=actor.id,
        target_type="community_member",
        target_id=str(member.id),
    )
    db.commit()
    db.refresh(member)
    return member


# =========================================================
# POST /community/members/{id}/reject
# =========================================================

def reject_member(
    db: DbSession,
    actor: User,
    member_id: uuid.UUID,
    reason: str | None = None,
) -> CommunityMember:
    admin_link = _require_community_admin(db, actor)
    member = db.get(CommunityMember, member_id)
    if member is None or member.community_id != admin_link.community_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    if member.status != "pending":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Cannot reject a member with status '{member.status}'",
        )

    member.status = "rejected"
    member.reviewed_by = actor.id
    member.reviewed_at = datetime.now(UTC)
    member.rejection_reason = (reason or "").strip() or None

    add_audit_log(
        db,
        "community.member_rejected",
        actor_user_id=actor.id,
        target_type="community_member",
        target_id=str(member.id),
        details={"reason": member.rejection_reason},
    )
    db.commit()
    db.refresh(member)
    return member


# =========================================================
# POST /community/join-link
# =========================================================

def generate_join_link(db: DbSession, actor: User) -> CommunityJoinLink:
    admin_link = _require_community_admin(db, actor)
    community_id = admin_link.community_id

    existing = db.scalars(
        select(CommunityJoinLink).where(
            CommunityJoinLink.community_id == community_id,
            CommunityJoinLink.is_active.is_(True),
        )
    ).all()
    for link in existing:
        link.is_active = False

    link = CommunityJoinLink(
        community_id=community_id,
        code=secrets.token_urlsafe(8),
        is_active=True,
        created_by=actor.id,
    )
    db.add(link)

    add_audit_log(
        db,
        "community.join_link_generated",
        actor_user_id=actor.id,
        target_type="community",
        target_id=str(community_id),
    )
    db.commit()
    db.refresh(link)
    return link


# =========================================================
# GET /community/join-link
# =========================================================

def get_join_link(db: DbSession, actor: User) -> CommunityJoinLink:
    admin_link = _require_community_admin(db, actor)
    link = db.scalar(
        select(CommunityJoinLink).where(
            CommunityJoinLink.community_id == admin_link.community_id,
            CommunityJoinLink.is_active.is_(True),
        )
    )
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No active join link")
    return link


# =========================================================
# DELETE /community/join-link
# =========================================================

def revoke_join_link(db: DbSession, actor: User) -> None:
    admin_link = _require_community_admin(db, actor)
    links = db.scalars(
        select(CommunityJoinLink).where(
            CommunityJoinLink.community_id == admin_link.community_id,
            CommunityJoinLink.is_active.is_(True),
        )
    ).all()
    if not links:
        return
    for link in links:
        link.is_active = False
    add_audit_log(
        db,
        "community.join_link_revoked",
        actor_user_id=actor.id,
        target_type="community",
        target_id=str(admin_link.community_id),
    )
    db.commit()


# =========================================================
# PUBLIC: preview + apply via join link
# =========================================================

def _get_join_link_by_code(db: DbSession, code: str) -> CommunityJoinLink:
    link = db.scalar(
        select(CommunityJoinLink).where(
            CommunityJoinLink.code == code,
            CommunityJoinLink.is_active.is_(True),
        )
    )
    if link is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "This join link is invalid or has been revoked",
        )
    if link.expires_at and link.expires_at <= datetime.now(UTC):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This join link has expired")
    return link


def preview_join_link(db: DbSession, code: str) -> dict:
    link = _get_join_link_by_code(db, code)
    community = db.get(Community, link.community_id)
    if community is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Community not found")

    return {
        "community_name": community.name,
        "community_type": community.type,
        "state_name": community.state.name,
        "lga_name": community.lga.name,
        "is_open": community.status == "active",
    }


def apply_via_join_link(
    db: DbSession,
    code: str,
    full_name: str,
    email: str,
    password: str,
    phone: str | None,
) -> None:
    link = _get_join_link_by_code(db, code)
    community = db.get(Community, link.community_id)
    if community is None or community.status != "active":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Community is not accepting applications",
        )

    normalized_email = email.strip().lower()

    existing = db.scalar(
        select(CommunityMember).where(
            CommunityMember.community_id == community.id,
            CommunityMember.email == normalized_email,
        )
    )
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "You already have a pending or approved request for this community",
        )

    existing_user = db.scalar(select(User).where(User.email == normalized_email))
    if existing_user is not None:
        user_id = existing_user.id
    else:
        now = datetime.now(UTC)
        parts = full_name.strip().split()
        first_name = parts[0] if parts else "Member"
        last_name = " ".join(parts[1:]) if len(parts) > 1 else ""

        new_user = User(
            email=normalized_email,
            password_hash=hash_password(password),
            first_name=first_name,
            last_name=last_name,
            phone=(phone or "").strip() or None,
            status=UserStatus.PENDING,
            email_verified_at=None,
            password_changed_at=now,
        )
        db.add(new_user)
        db.flush()
        user_id = new_user.id

    member = CommunityMember(
        community_id=community.id,
        user_id=user_id,
        full_name=full_name.strip(),
        email=normalized_email,
        method="open_link",
        status="pending",
    )
    db.add(member)

    add_audit_log(
        db,
        "community.member_applied",
        target_type="community_member",
        target_id=str(member.id),
        details={"email": normalized_email, "community_id": str(community.id)},
    )
    db.commit()


# =========================================================
# PUBLIC: accept member invite (token-based)
# =========================================================

def accept_member_invite(
    db: DbSession,
    raw_token: str,
    password: str,
    phone: str | None,
) -> dict:
    invite = db.scalar(
        select(Invite).where(
            Invite.token_hash == hash_token(raw_token),
            Invite.purpose == INVITE_PURPOSE_MEMBER,
        )
    )
    if invite is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invalid invite link")

    now = datetime.now(UTC)
    if invite.status != "pending":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This invite is no longer valid")
    if invite.expires_at <= now:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This invite has expired")

    member = db.scalar(
        select(CommunityMember).where(
            CommunityMember.community_id == invite.community_id,
            CommunityMember.email == invite.email,
            CommunityMember.status == "pending",
        )
    )
    if member is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Member record not found")

    existing_user = db.scalar(select(User).where(User.email == invite.email))
    if existing_user is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "An account with this email already exists. Please log in.",
        )

    user = User(
        email=invite.email,
        password_hash=hash_password(password),
        first_name=invite.first_name or "Member",
        last_name=invite.last_name or "",
        phone=(phone or "").strip() or None,
        status=UserStatus.ACTIVE,
        email_verified_at=now,
        password_changed_at=now,
    )
    db.add(user)
    db.flush()

    member.user_id = user.id
    member.status = "approved"
    member.joined_at = now

    invite.status = "accepted"
    invite.accepted_at = now
    invite.accepted_by = user.id

    add_audit_log(
        db,
        "community.member_invite_accepted",
        actor_user_id=user.id,
        target_type="community_member",
        target_id=str(member.id),
    )
    db.commit()

    return {
        "status": "accepted",
        "user_id": user.id,
        "community_id": invite.community_id,
    }