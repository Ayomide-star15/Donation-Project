import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as DbSession

from app.modules.communities.models import (
    Community,
    CommunityAdmin,
    CommunityMember,
)
from app.modules.requests.models import BloodRequest
from app.modules.users.models import User


# =========================================================
# Activity level thresholds
# =========================================================
ACTIVITY_HIGH = 20       # requests + 2 * donations
ACTIVITY_MEDIUM = 5
ACTIVITY_WINDOW_DAYS = 30


def _compute_activity_level(score: int) -> str:
    if score >= ACTIVITY_HIGH:
        return "high"
    if score >= ACTIVITY_MEDIUM:
        return "medium"
    return "low"


def _get_admin_info(db: DbSession, community_id: uuid.UUID) -> dict | None:
    """Return the active admin for this community, or None."""
    row = db.execute(
        select(User.id, User.first_name, User.last_name, User.email)
        .select_from(CommunityAdmin)
        .join(User, User.id == CommunityAdmin.user_id)
        .where(
            CommunityAdmin.community_id == community_id,
            CommunityAdmin.status == "active",
        )
        .limit(1)
    ).first()

    if row is None:
        return None

    return {
        "id": row[0],
        "full_name": f"{row[1]} {row[2]}".strip(),
        "email": row[3],
    }


# =========================================================
# LIST COMMUNITIES
# =========================================================

def list_communities(
    db: DbSession,
    *,
    status_filter: str | None = None,
    activity_filter: str | None = None,
    state_filter: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Super Admin: list all communities with counts + activity."""
    window_start = datetime.now(UTC) - timedelta(days=ACTIVITY_WINDOW_DAYS)

    stmt = select(Community)
    count_stmt = select(func.count(Community.id))

    if status_filter:
        stmt = stmt.where(Community.status == status_filter)
        count_stmt = count_stmt.where(Community.status == status_filter)

    if state_filter:
        stmt = stmt.where(Community.state.has(name=state_filter))
        count_stmt = count_stmt.where(Community.state.has(name=state_filter))

    if search:
        like = f"%{search.lower()}%"
        cond = func.lower(Community.name).like(like)
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)

    stmt = stmt.order_by(Community.created_at.desc()).limit(limit).offset(offset)

    rows = list(db.scalars(stmt))
    total = db.scalar(count_stmt) or 0

    # Batch counts
    community_ids = [c.id for c in rows]

    member_count_map: dict[uuid.UUID, int] = {}
    requests_map: dict[uuid.UUID, int] = {}
    donations_map: dict[uuid.UUID, int] = {}

    if community_ids:
        member_rows = db.execute(
            select(
                CommunityMember.community_id,
                func.count(CommunityMember.id),
            )
            .where(
                CommunityMember.community_id.in_(community_ids),
                CommunityMember.status == "approved",
            )
            .group_by(CommunityMember.community_id)
        ).all()
        member_count_map = {cid: n for cid, n in member_rows}

        request_rows = db.execute(
            select(
                BloodRequest.community_id,
                func.count(BloodRequest.id),
            )
            .where(
                BloodRequest.community_id.in_(community_ids),
                BloodRequest.created_at > window_start,
            )
            .group_by(BloodRequest.community_id)
        ).all()
        requests_map = {cid: n for cid, n in request_rows}

        donation_rows = db.execute(
            select(
                BloodRequest.community_id,
                func.count(BloodRequest.id),
            )
            .where(
                BloodRequest.community_id.in_(community_ids),
                BloodRequest.status == "fulfilled",
                BloodRequest.closed_at > window_start,
            )
            .group_by(BloodRequest.community_id)
        ).all()
        donations_map = {cid: n for cid, n in donation_rows}

    communities = []
    for c in rows:
        admin_info = _get_admin_info(db, c.id)

        requests_30d = requests_map.get(c.id, 0)
        donations_30d = donations_map.get(c.id, 0)
        score = requests_30d + (donations_30d * 2)
        activity_level = _compute_activity_level(score)

        # Apply activity filter after computing (it's derived, not stored)
        if activity_filter and activity_level != activity_filter:
            continue

        communities.append({
            "id": c.id,
            "name": c.name,
            "type": c.type,
            "state_name": c.state.name,
            "lga_name": c.lga.name,
            "status": c.status,
            "admin": admin_info,
            "member_count": member_count_map.get(c.id, 0),
            "activity_level": activity_level,
            "created_at": c.created_at,
        })

    # If we filtered by activity, total reflects the filtered set
    final_total = len(communities) if activity_filter else total

    return {
        "communities": communities,
        "total": final_total,
        "limit": limit,
        "offset": offset,
    }


# =========================================================
# GET ONE COMMUNITY
# =========================================================

def get_community_detail(db: DbSession, community_id: uuid.UUID) -> dict:
    """Super Admin: full detail for one community."""
    community = db.get(Community, community_id)
    if community is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Community not found")

    window_start = datetime.now(UTC) - timedelta(days=ACTIVITY_WINDOW_DAYS)

    # Counts
    member_count = db.scalar(
        select(func.count(CommunityMember.id)).where(
            CommunityMember.community_id == community_id,
            CommunityMember.status == "approved",
        )
    ) or 0

    total_requests = db.scalar(
        select(func.count(BloodRequest.id)).where(
            BloodRequest.community_id == community_id
        )
    ) or 0

    fulfilled_requests = db.scalar(
        select(func.count(BloodRequest.id)).where(
            BloodRequest.community_id == community_id,
            BloodRequest.status == "fulfilled",
        )
    ) or 0

    open_requests = db.scalar(
        select(func.count(BloodRequest.id)).where(
            BloodRequest.community_id == community_id,
            BloodRequest.status.in_(["open", "partial"]),
        )
    ) or 0

    # Admin
    admin_info = _get_admin_info(db, community_id)

    # Recent requests (last 3)
    recent_rows = list(
        db.scalars(
            select(BloodRequest)
            .where(BloodRequest.community_id == community_id)
            .order_by(BloodRequest.created_at.desc())
            .limit(3)
        )
    )

    recent_requests = [
        {
            "id": r.id,
            "reference_code": r.reference_code,
            "blood_type_needed": r.blood_type_needed,
            "status": r.status,
            "created_at": r.created_at,
        }
        for r in recent_rows
    ]

    return {
        "id": community.id,
        "name": community.name,
        "type": community.type,
        "state_name": community.state.name,
        "lga_name": community.lga.name,
        "status": community.status,
        "created_at": community.created_at,
        "updated_at": community.updated_at,
        "stats": {
            "member_count": member_count,
            "total_requests": total_requests,
            "fulfilled_requests": fulfilled_requests,
            "open_requests": open_requests,
        },
        "admin": admin_info,
        "recent_requests": recent_requests,
    }