import logging
import hashlib
import uuid
import secrets
from datetime import UTC, datetime, timedelta
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.modules.audit.service import add_audit_log
from app.modules.communities.models import CommunityMember
from app.modules.hospitals.models import Hospital
from app.modules.requests.models import (
    BloodRequest,
    DonorAcceptance
)
from app.modules.requests.schemas import CreateRequestPayload
from app.modules.users.models import User
from app.modules.donors.models import DonorProfile

logger = logging.getLogger(__name__)

REQUEST_COOLDOWN_HOURS = 72
REQUEST_EXPIRY_HOURS = 72
ACCEPTANCE_EXPIRY_HOURS = 24
DONOR_ACCEPTANCE_COOLDOWN_DAYS = 90


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

def _generate_verification_code() -> str:
    """Generate a 6-digit numeric code."""
    return f"{secrets.randbelow(1_000_000):06d}"


def _hash_code(code: str) -> str:
    """SHA-256 hash of the code — never store the raw value."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _donor_is_eligible(donor: DonorProfile) -> tuple[bool, str | None]:
    """Return (is_eligible, reason_if_not)."""
    if not donor.availability:
        return False, "You have marked yourself as unavailable"

    if not donor.is_genotype_eligible:
        return False, "Your genotype makes you ineligible to donate"

    if donor.last_donation_date:
        eligible_on = donor.last_donation_date + timedelta(days=DONOR_COOLDOWN_DAYS)
        if eligible_on > datetime.now(UTC).date():
            return False, f"You are in cooldown until {eligible_on.isoformat()}"

    return True, None


def accept_request(
    db: DbSession,
    actor: User,
    request_id: uuid.UUID,
) -> dict:
    """A donor accepts a request and receives a verification code."""
    now = datetime.now(UTC)

    # ---- Rule 1: must be a registered donor ----
    donor = db.get(DonorProfile, actor.id)
    if donor is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only registered donors can accept requests",
        )

    # ---- Rule 2: must be eligible ----
    is_eligible, reason = _donor_is_eligible(donor)
    if not is_eligible:
        raise HTTPException(status.HTTP_403_FORBIDDEN, reason or "Not eligible")

    # ---- Rule 3: lock the request row (race condition protection) ----
    request = db.scalar(
        select(BloodRequest)
        .where(BloodRequest.id == request_id)
        .with_for_update()
    )
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")

    # ---- Rule 4: request must be open or partial ----
    if request.status not in ("open", "partial"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This request is no longer accepting donors",
        )

    # ---- Rule 5: still has slots ----
    if request.accepted_count >= request.donors_needed:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This request just filled up",
        )

    # ---- Rule 6: request not expired ----
    if request.expires_at <= now:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This request has expired",
        )

    # ---- Rule 7: blood type compatibility ----
    from app.modules.donors.compatibility import recipient_types_donor_can_help
    if request.blood_type_needed not in recipient_types_donor_can_help(donor.blood_type):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Your blood type is not compatible with this request",
        )

    # ---- Rule 8: donor has no other active acceptance ----
    active_acceptance = db.scalar(
        select(DonorAcceptance).where(
            DonorAcceptance.donor_id == actor.id,
            DonorAcceptance.status == "accepted",
        )
    )
    if active_acceptance is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "You already have an active acceptance. Cancel it before accepting another.",
        )

    # ---- Rule 9: donor hasn't already accepted this request ----
    existing = db.scalar(
        select(DonorAcceptance).where(
            DonorAcceptance.donor_id == actor.id,
            DonorAcceptance.request_id == request_id,
        )
    )
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "You have already accepted this request",
        )

    # ---- Generate code + create acceptance ----
    code = _generate_verification_code()
    acceptance = DonorAcceptance(
        request_id=request.id,
        donor_id=actor.id,
        verification_code_hash=_hash_code(code),
        status="accepted",
        expires_at=now + timedelta(hours=ACCEPTANCE_EXPIRY_HOURS),
    )
    db.add(acceptance)

    # ---- Increment request count ----
    request.accepted_count += 1

    # ---- Audit log ----
    add_audit_log(
        db,
        "acceptance.created",
        actor_user_id=actor.id,
        target_type="blood_request",
        target_id=str(request.id),
        details={
            "reference_code": request.reference_code,
            "acceptance_id": str(acceptance.id),
        },
    )
    db.commit()
    db.refresh(acceptance)
    db.refresh(request)

    # ---- Return ----
    return {
        "acceptance_id": acceptance.id,
        "verification_code": code,
        "status": "accepted",
        "expires_at": acceptance.expires_at,
        "request": {
            "id": request.id,
            "reference_code": request.reference_code,
            "blood_type_needed": request.blood_type_needed,
            "urgency": request.urgency,
        },
        "hospital": {
            "id": request.hospital.id,
            "name": request.hospital.name,
            "address": request.hospital.address,
            "lga_name": request.hospital.lga.name,
            "state_name": request.hospital.state.name,
            "phone": request.hospital.phone,
        },
        "message": "Show this code at the hospital when you donate.",
    }