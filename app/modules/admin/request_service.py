import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.modules.communities.models import Community
from app.modules.requests.models import BloodRequest, DonorAcceptance
from app.modules.users.models import User


# =========================================================
# LIST REQUESTS
# =========================================================
def list_requests(
    db: DbSession,
    *,
    status_filter: str | None = None,
    urgency_filter: str | None = None,
    blood_type_filter: str | None = None,
    community_id: uuid.UUID | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Super Admin: list all requests across every community."""
    stmt = (
        select(BloodRequest, Community)
        .join(Community, Community.id == BloodRequest.community_id)
    )

    if status_filter:
        stmt = stmt.where(BloodRequest.status == status_filter)
    if urgency_filter:
        stmt = stmt.where(BloodRequest.urgency == urgency_filter)
    if blood_type_filter:
        stmt = stmt.where(BloodRequest.blood_type_needed == blood_type_filter)
    if community_id:
        stmt = stmt.where(BloodRequest.community_id == community_id)
    if search:
        like = f"%{search.lower()}%"
        stmt = stmt.where(
            func.lower(BloodRequest.reference_code).like(like)
        )

    stmt = (
        stmt.order_by(BloodRequest.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    rows = db.execute(stmt).all()

    requests = []
    for req, comm in rows:
        requests.append({
            "id": req.id,
            "reference_code": req.reference_code,
            "blood_type_needed": req.blood_type_needed,
            "donors_needed": req.donors_needed,
            "accepted_count": req.accepted_count,
            "confirmed_count": req.confirmed_count,
            "status": req.status,
            "urgency": req.urgency,
            "hospital": {
                "id": req.hospital.id,
                "name": req.hospital.name,
                "lga_name": req.hospital.lga.name,
                "state_name": req.hospital.state.name,
            },
            "community": {
                "id": comm.id,
                "name": comm.name,
            },
            "created_at": req.created_at,
        })

    return {
        "requests": requests,
        "limit": limit,
        "offset": offset,
    }

def _community_name(db: DbSession, community_id: uuid.UUID) -> str:
    community = db.get(Community, community_id)
    return community.name if community else ""


# =========================================================
# GET ONE REQUEST
# =========================================================

def get_request_detail(db: DbSession, request_id: uuid.UUID) -> dict:
    """Super Admin: full detail for one request."""
    request = db.get(BloodRequest, request_id)
    if request is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Request not found",
        )

    # ---- Requester ----
    requester = db.get(User, request.requester_id)
    if requester is None:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Requester not found",
        )

    # ---- Community ----
    community = db.get(Community, request.community_id)

    # ---- Donor slots (anonymous — no identities) ----
    acceptances = list(
        db.scalars(
            select(DonorAcceptance)
            .where(DonorAcceptance.request_id == request_id)
            .order_by(DonorAcceptance.accepted_at.asc())
        )
    )

    donor_slots = [
        {
            "slot": i + 1,
            "status": a.status,
            "confirmed_at": a.confirmed_at,
        }
        for i, a in enumerate(acceptances)
    ]

    return {
        "id": request.id,
        "reference_code": request.reference_code,
        "status": request.status,
        "blood_type_needed": request.blood_type_needed,
        "donors_needed": request.donors_needed,
        "accepted_count": request.accepted_count,
        "confirmed_count": request.confirmed_count,
        "donors_left": request.donors_needed - request.accepted_count,
        "urgency": request.urgency,
        "notes": request.notes,
        "created_at": request.created_at,
        "expires_at": request.expires_at,
        "closed_at": request.closed_at,
        "hospital": {
            "id": request.hospital.id,
            "name": request.hospital.name,
            "address": request.hospital.address,
            "lga_name": request.hospital.lga.name,
            "state_name": request.hospital.state.name,
            "phone": request.hospital.phone,
        },
        "requester": {
            "id": requester.id,
            "full_name": (
                f"{requester.first_name} {requester.last_name}".strip()
            ),
            "phone": requester.phone,
            "email": requester.email,
            "role": "member",
        },
        "community": {
            "id": community.id if community else None,
            "name": community.name if community else "",
            "type": community.type if community else "",
            "state_name": (
                community.state.name
                if community and community.state
                else ""
            ),
        },
        "donor_slots": donor_slots,
    }