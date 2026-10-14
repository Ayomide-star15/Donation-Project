import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session as DbSession

from app.core.enums import AuditOutcome, UserStatus
from app.modules.audit.service import add_audit_log
from app.modules.auth.models import Session as SessionModel
from app.modules.communities.models import CommunityMember
from app.modules.donors.models import DonorProfile
from app.modules.users.models import Role, User, UserRole


# =========================================================
# LIST USERS
# =========================================================

def list_users(
    db: DbSession,
    *,
    status_filter: UserStatus | None = None,
    role_filter: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    stmt = select(User)
    count_stmt = select(func.count(User.id))

    if status_filter is not None:
        stmt = stmt.where(User.status == status_filter)
        count_stmt = count_stmt.where(User.status == status_filter)

    if role_filter:
        subq = (
            select(UserRole.user_id)
            .join(Role, Role.id == UserRole.role_id)
            .where(Role.name == role_filter)
        )
        stmt = stmt.where(User.id.in_(subq))
        count_stmt = count_stmt.where(User.id.in_(subq))

    if search:
        like = f"%{search.lower()}%"
        cond = or_(
            func.lower(User.email).like(like),
            func.lower(User.first_name).like(like),
            func.lower(User.last_name).like(like),
            func.lower(User.user_code).like(like),
        )
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)

    stmt = stmt.order_by(User.created_at.desc()).limit(limit).offset(offset)

    rows = list(db.scalars(stmt))
    total = db.scalar(count_stmt) or 0

    # Preload roles per user in one query
    user_ids = [u.id for u in rows]
    roles_map: dict[uuid.UUID, list[str]] = {uid: [] for uid in user_ids}
    donor_ids: set[uuid.UUID] = set()
    member_ids: set[uuid.UUID] = set()

    if user_ids:
        role_rows = db.execute(
            select(UserRole.user_id, Role.name)
            .join(Role, Role.id == UserRole.role_id)
            .where(UserRole.user_id.in_(user_ids))
        ).all()
        for uid, name in role_rows:
            roles_map[uid].append(name)

        donor_ids = {
            pid for pid in db.scalars(
                select(DonorProfile.profile_id).where(
                    DonorProfile.profile_id.in_(user_ids)
                )
            ) if pid is not None
        }

        member_ids = {
            uid for uid in db.scalars(
                select(CommunityMember.user_id).where(
                    CommunityMember.user_id.in_(user_ids),
                    CommunityMember.status == "approved",
                )
            ) if uid is not None
        }

    users = []
    for u in rows:
        users.append({
            "id": u.id,
            "user_code": u.user_code,
            "email": u.email,
            "first_name": u.first_name,
            "last_name": u.last_name,
            "phone": u.phone,
            "status": u.status,
            "email_verified_at": u.email_verified_at,
            "last_login_at": u.last_login_at,
            "created_at": u.created_at,
            "roles": roles_map.get(u.id, []),
            "is_donor": u.id in donor_ids,
            "is_member": u.id in member_ids,
        })

    return {"users": users, "total": total, "limit": limit, "offset": offset}


# =========================================================
# GET ONE USER
# =========================================================

def get_user_detail(db: DbSession, user_id: uuid.UUID) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")

    # Roles
    role_rows = db.execute(
        select(Role.name, Role.description)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id)
    ).all()
    roles = [{"name": r[0], "description": r[1]} for r in role_rows]

    # Donor?
    donor = db.get(DonorProfile, user.id)
    donor_profile = None
    if donor is not None:
        donor_profile = {
            "blood_type": donor.blood_type,
            "is_genotype_eligible": donor.is_genotype_eligible,
            "state_name": donor.state.name,
            "lga_name": donor.lga.name,
            "availability": donor.availability,
            "last_donation_date": donor.last_donation_date.isoformat()
            if donor.last_donation_date
            else None,
        }

    # Membership?
    member = db.scalar(
        select(CommunityMember).where(
            CommunityMember.user_id == user.id,
            CommunityMember.status == "approved",
        )
    )
    community_membership = None
    if member is not None:
        community_membership = {
            "community_id": str(member.community_id),
            "community_name": member.community.name if member.community else None,
            "status": member.status,
            "joined_at": member.joined_at.isoformat() if member.joined_at else None,
        }

    return {
        "id": user.id,
        "user_code": user.user_code,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone": user.phone,
        "status": user.status,
        "email_verified_at": user.email_verified_at,
        "last_login_at": user.last_login_at,
        "failed_login_attempts": user.failed_login_attempts,
        "locked_until": user.locked_until,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "roles": roles,
        "is_donor": donor is not None,
        "is_member": member is not None,
        "donor_profile": donor_profile,
        "community_membership": community_membership,
    }


# =========================================================
# CHANGE STATUS (suspend / ban / reactivate)
# =========================================================

def _get_target_user(db: DbSession, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    return user


def _check_not_super_admin(db: DbSession, user: User) -> None:
    """Super Admin accounts cannot be suspended or banned."""
    is_super = db.scalar(
        select(UserRole.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(UserRole.user_id == user.id, Role.name == "super_admin")
    )
    if is_super is not None:
        raise HTTPException(
            400,
            "Super Admin accounts cannot be suspended or banned",
        )


def _revoke_all_sessions(db: DbSession, user_id: uuid.UUID, reason: str) -> None:
    db.execute(
        update(SessionModel)
        .where(SessionModel.user_id == user_id, SessionModel.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC), revocation_reason=reason)
    )


def suspend_user(
    db: DbSession,
    actor: User,
    user_id: uuid.UUID,
    reason: str | None,
) -> dict:
    if user_id == actor.id:
        raise HTTPException(400, "You cannot suspend your own account")

    user = _get_target_user(db, user_id)
    _check_not_super_admin(db, user)

    if user.status == UserStatus.SUSPENDED:
        raise HTTPException(400, "User is already suspended")
    if user.status == UserStatus.BANNED:
        raise HTTPException(400, "User is banned. Use reactivate to unban.")

    previous = user.status
    user.status = UserStatus.SUSPENDED
    _revoke_all_sessions(db, user.id, "suspended_by_admin")

    add_audit_log(
        db,
        "admin.user_suspended",
        actor_user_id=actor.id,
        outcome=AuditOutcome.SUCCESS,
        target_type="user",
        target_id=str(user.id),
        details={
            "previous_status": previous.value if hasattr(previous, "value") else previous,
            "reason": reason,
        },
    )
    db.commit()

    return {
        "status": "suspended",
        "user_id": user.id,
        "new_status": UserStatus.SUSPENDED,
        "message": "User suspended. All sessions revoked.",
    }


def ban_user(
    db: DbSession,
    actor: User,
    user_id: uuid.UUID,
    reason: str | None,
) -> dict:
    if user_id == actor.id:
        raise HTTPException(400, "You cannot ban your own account")

    user = _get_target_user(db, user_id)
    _check_not_super_admin(db, user)

    if user.status == UserStatus.BANNED:
        raise HTTPException(400, "User is already banned")

    previous = user.status
    user.status = UserStatus.BANNED
    _revoke_all_sessions(db, user.id, "banned_by_admin")

    add_audit_log(
        db,
        "admin.user_banned",
        actor_user_id=actor.id,
        outcome=AuditOutcome.SUCCESS,
        target_type="user",
        target_id=str(user.id),
        details={
            "previous_status": previous.value if hasattr(previous, "value") else previous,
            "reason": reason,
        },
    )
    db.commit()

    return {
        "status": "banned",
        "user_id": user.id,
        "new_status": UserStatus.BANNED,
        "message": "User banned. All sessions revoked.",
    }


def reactivate_user(
    db: DbSession,
    actor: User,
    user_id: uuid.UUID,
    reason: str | None,
) -> dict:
    user = _get_target_user(db, user_id)

    if user.status == UserStatus.ACTIVE:
        raise HTTPException(400, "User is already active")

    if user.status not in (UserStatus.SUSPENDED, UserStatus.BANNED, UserStatus.DISABLED):
        raise HTTPException(400, f"Cannot reactivate a {user.status.value} user")

    previous = user.status
    user.status = UserStatus.ACTIVE

    add_audit_log(
        db,
        "admin.user_reactivated",
        actor_user_id=actor.id,
        outcome=AuditOutcome.SUCCESS,
        target_type="user",
        target_id=str(user.id),
        details={
            "previous_status": previous.value if hasattr(previous, "value") else previous,
            "reason": reason,
        },
    )
    db.commit()

    return {
        "status": "active",
        "user_id": user.id,
        "new_status": UserStatus.ACTIVE,
        "message": "User reactivated.",
    }