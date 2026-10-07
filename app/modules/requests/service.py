import logging
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.modules.audit.service import add_audit_log
from app.modules.communities.models import CommunityMember
from app.modules.hospitals.models import Hospital
from app.modules.requests.models import BloodRequest
from app.modules.requests.schemas import CreateRequestPayload
from app.modules.users.models import User


logger = logging.getLogger(__name__)

REQUEST_COOLDOWN_HOURS = 72
REQUEST_EXPIRY_HOURS = 72


def _next_reference_code(db: DbSession) -> str:
    """Generate REQ-0001, REQ-0002, ..."""
    count = db.scalar(select(func.count(BloodRequest.id))) or 0
    return f"REQ-{count + 1:04d}"


def _serialize_request(req: BloodRequest) -> dict:
    return {
        "id": req.id,
        "reference_code": req.reference_code,
        "blood_type_needed": req.blood_type_needed,
        "donors_needed": req.donors_needed,
        "urgency": req.urgency,
        "notes": req.notes,
        "status": req.status,
        "accepted_count": req.accepted_count,
        "confirmed_count": req.confirmed_count,
        "requester_cooldown_until": req.requester_cooldown_until,
        "expires_at": req.expires_at,
        "created_at": req.created_at,
        "hospital": {
            "id": req.hospital.id,
            "name": req.hospital.name,
            "address": req.hospital.address,
            "state_name": req.hospital.state.name,
            "lga_name": req.hospital.lga.name,
            "phone": req.hospital.phone,
        },
    }


def create_request(
    db: DbSession,
    actor: User,
    payload: CreateRequestPayload,
) -> dict:
    now = datetime.now(UTC)

    # ---- Rule 1: must be an active community member ----
    membership = db.scalar(
        select(CommunityMember).where(
            CommunityMember.user_id == actor.id,
            CommunityMember.status == "approved",
        )
    )
    if membership is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only active community members can raise blood requests",
        )

    # ---- Rule 2: must not be in cooldown ----
    in_cooldown = db.scalar(
        select(BloodRequest).where(
            BloodRequest.requester_id == actor.id,
            BloodRequest.status.in_(["open", "partial"]),
            BloodRequest.requester_cooldown_until > now,
        )
    )
    if in_cooldown is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            (
                f"You're in cooldown until "
                f"{in_cooldown.requester_cooldown_until.isoformat()}. "
                "Ask your Community Admin to request early reactivation."
            ),
        )

    # ---- Rule 3: hospital must exist and be active ----
    hospital = db.get(Hospital, payload.hospital_id)
    if hospital is None or not hospital.is_active:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Hospital not found or inactive",
        )

    cooldown_until = now + timedelta(hours=REQUEST_COOLDOWN_HOURS)
    expires_at = now + timedelta(hours=REQUEST_EXPIRY_HOURS)

    request = BloodRequest(
        reference_code=_next_reference_code(db),
        requester_id=actor.id,
        community_id=membership.community_id,
        hospital_id=hospital.id,
        blood_type_needed=payload.blood_type_needed.value,
        donors_needed=payload.donors_needed,
        urgency=payload.urgency.value,
        notes=(payload.notes or "").strip() or None,
        status="open",
        requester_cooldown_until=cooldown_until,
        expires_at=expires_at,
    )
    db.add(request)
    db.flush()

    add_audit_log(
        db,
        "request.created",
        actor_user_id=actor.id,
        target_type="blood_request",
        target_id=str(request.id),
        details={
            "reference_code": request.reference_code,
            "blood_type_needed": request.blood_type_needed,
            "donors_needed": request.donors_needed,
            "hospital": hospital.name,
        },
    )
    db.commit()
    db.refresh(request)
    return _serialize_request(request)