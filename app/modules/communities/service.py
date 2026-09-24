import logging
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.core.enums import UserStatus
from app.core.security import hash_password, hash_token
from app.modules.audit.service import add_audit_log
from app.modules.communities.models import Community, CommunityAdmin
from app.modules.communities.schemas import AcceptInviteRequest
from app.modules.invites.models import Invite
from app.modules.locations.models import Lga, State
from app.modules.users.models import Role, User, UserRole


logger = logging.getLogger(__name__)

INVITE_PURPOSE = "community_admin"
COMMUNITY_ADMIN_ROLE = "community_admin"


# ---------- Public: view invite ----------

def get_invite_details(db: DbSession, raw_token: str) -> dict:
    invite = _find_invite(db, raw_token)
    inviter = db.get(User, invite.invited_by)

    now = datetime.now(UTC)
    return {
        "first_name": invite.first_name,
        "last_name": invite.last_name,
        "email": invite.email,
        "community_name": invite.community_name,
        "invited_by_name": (
            f"{inviter.first_name} {inviter.last_name}".strip()
            if inviter
            else "LifeLink"
        ),
        "expires_at": invite.expires_at,
        "is_expired": invite.expires_at <= now,
        "is_used": invite.status != "pending",
    }


# ---------- Public: accept invite ----------

def accept_invite(
    db: DbSession,
    raw_token: str,
    payload: AcceptInviteRequest,
) -> dict:
    invite = _find_invite(db, raw_token)
    _assert_usable(invite)

    # Reject if user with this email already exists
    if db.scalar(select(User.id).where(User.email == invite.email)):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "An account with this email already exists. Please log in instead.",
        )

    # Validate location
    state = db.get(State, payload.state_id)
    if state is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown state"
        )

    lga = db.get(Lga, payload.lga_id)
    if lga is None or lga.state_id != state.id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"LGA does not belong to {state.name}",
        )

    now = datetime.now(UTC)

    # ---- 1. Create user ----
    user = User(
        email=invite.email,
        password_hash=hash_password(payload.password),
        first_name=invite.first_name,
        last_name=invite.last_name,
        phone=(payload.phone or "").strip() or None,
        status=UserStatus.ACTIVE,
        email_verified_at=now,          # invite link proved ownership
        password_changed_at=now,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "An account with this email already exists",
        )

    # ---- 2. Grant community_admin role ----
    role = db.scalar(select(Role).where(Role.name == COMMUNITY_ADMIN_ROLE))
    if role is None:
        role = Role(
            name=COMMUNITY_ADMIN_ROLE,
            description="Manages a LifeLink community",
            is_system=True,
        )
        db.add(role)
        db.flush()

    db.add(UserRole(user_id=user.id, role_id=role.id))

    # ---- 3. Create the community ----
    community = Community(
        name=invite.community_name,
        type=payload.community_type.value,
        state_id=state.id,
        lga_id=lga.id,
        created_by=invite.invited_by,
    )
    db.add(community)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"A community named '{invite.community_name}' already exists in "
            f"{state.name} / {lga.name}",
        )

    # ---- 4. Link user → community ----
    db.add(CommunityAdmin(
        community_id=community.id,
        user_id=user.id,
        status="active",
        invited_by=invite.invited_by,
    ))

    # ---- 5. Mark invite accepted ----
    invite.status = "accepted"
    invite.accepted_at = now
    invite.accepted_by = user.id

    add_audit_log(
        db,
        "invite.accepted",
        actor_user_id=user.id,
        target_type="community",
        target_id=str(community.id),
        details={
            "email": invite.email,
            "community_name": invite.community_name,
        },
    )
    db.commit()
    db.refresh(community)

    return {
        "status": "accepted",
        "user_id": user.id,
        "community": {
            "id": community.id,
            "name": community.name,
            "type": community.type,
            "state_id": community.state_id,
            "lga_id": community.lga_id,
            "state_name": state.name,
            "lga_name": lga.name,
            "status": community.status,
            "created_at": community.created_at,
        },
    }


# ---------- Public: decline invite ----------

def decline_invite(db: DbSession, raw_token: str) -> None:
    invite = _find_invite(db, raw_token)
    _assert_usable(invite)
    invite.status = "declined"
    invite.declined_at = datetime.now(UTC)

    add_audit_log(
        db,
        "invite.declined",
        target_type="invite",
        target_id=str(invite.id),
        details={"email": invite.email},
    )
    db.commit()


# ---------- Helpers ----------

def _find_invite(db: DbSession, raw_token: str) -> Invite:
    invite = db.scalar(
        select(Invite).where(
            Invite.token_hash == hash_token(raw_token),
            Invite.purpose == INVITE_PURPOSE,
        )
    )
    if invite is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invalid invite link")
    return invite


def _assert_usable(invite: Invite) -> None:
    now = datetime.now(UTC)
    if invite.status == "revoked":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This invite has been revoked")
    if invite.status == "accepted":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This invite has already been used")
    if invite.status == "declined":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This invite was declined")
    if invite.expires_at <= now:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This invite has expired")