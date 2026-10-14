from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.core.enums import UserStatus
from app.modules.communities.models import Community
from app.modules.donors.models import DonorProfile
from app.modules.requests.models import BloodRequest, DonorAcceptance
from app.modules.users.models import User


def _enum_value(value):
    """Return string value for SQLAlchemy Enum or plain string."""
    return value.value if hasattr(value, "value") else str(value)


def get_dashboard(db: DbSession, *, recent_limit: int = 5) -> dict:
    """Super Admin dashboard summary + recent activity."""
    now = datetime.now(UTC)
    one_week_ago = now - timedelta(days=7)

    # =====================================================
    # 1. KPI CARD METRICS (matching the screenshots)
    # =====================================================


    # Total Donations = confirmed donor acceptances
    total_donations = db.scalar(
        select(func.count(DonorAcceptance.id)).where(
            DonorAcceptance.status == "confirmed"
        )
    ) or 0

    # Donations this week
    donations_this_week = db.scalar(
        select(func.count(DonorAcceptance.id)).where(
            DonorAcceptance.status == "confirmed",
            DonorAcceptance.confirmed_at >= one_week_ago,
        )
    ) or 0

    # Active Requests = open + partial
    active_requests = db.scalar(
        select(func.count(BloodRequest.id)).where(
            BloodRequest.status.in_(["open", "partial"])
        )
    ) or 0

    # Pending Overrides
    # NOTE: Assumed logic. Update this based on your actual business rule.
    # Example: Requests asking for more than 10 donors (which requires an admin override)
    pending_overrides = db.scalar(
        select(func.count(BloodRequest.id)).where(
            BloodRequest.status.in_(["open", "partial"]),
            BloodRequest.donors_needed > 10,
        )
    ) or 0

    # Cooldown Pool = donors temporarily unavailable
    # Option A: using availability field
    cooldown_pool = db.scalar(
        select(func.count(DonorProfile.profile_id)).where(
            DonorProfile.availability == False
        )
    ) or 0

    # Communities
    total_communities = db.scalar(select(func.count(Community.id))) or 0
    active_communities = db.scalar(
        select(func.count(Community.id)).where(Community.status == "active")
    ) or 0

    # =====================================================
    # 2. EXTRA PLATFORM HEALTH METRICS
    # =====================================================

    user_status_rows = db.execute(
        select(User.status, func.count(User.id)).group_by(User.status)
    ).all()
    user_counts = {_enum_value(status): count for status, count in user_status_rows}
    total_users = sum(user_counts.values())
    active_users = user_counts.get(UserStatus.ACTIVE.value, 0)

    total_donors = db.scalar(select(func.count(DonorProfile.profile_id))) or 0

    # =====================================================
    # 3. RECENT ACTIVITY
    # =====================================================

    recent_requests = []
    for request in db.scalars(
        select(BloodRequest)
        .order_by(BloodRequest.created_at.desc())
        .limit(recent_limit)
    ):
        recent_requests.append(
            {
                "id": str(request.id),
                "reference_code": request.reference_code,
                "blood_type_needed": request.blood_type_needed,
                "status": _enum_value(request.status),
                "urgency": _enum_value(request.urgency),
                "community_name": request.community.name if request.community else "",
                "created_at": request.created_at,
            }
        )

    # =====================================================
    # 4. RESPONSE
    # =====================================================
    return {
        "generated_at": now,
        "stats": {
            "total_donations": total_donations,
            "donations_this_week": donations_this_week,
            "active_requests": active_requests,
            "pending_overrides": pending_overrides,
            "cooldown_pool": cooldown_pool,
            "total_communities": total_communities,
            "active_communities": active_communities,
            "total_users": total_users,
            "active_users": active_users,
            "total_donors": total_donors,
        },
        "recent_requests": recent_requests,
    }