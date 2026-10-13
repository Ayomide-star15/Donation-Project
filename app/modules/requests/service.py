import logging
import hashlib
import uuid
import secrets
from datetime import UTC, datetime, timedelta
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession
from app.modules.donors.compatibility import recipient_types_donor_can_help
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
from app.modules.locations.models import Lga, State

logger = logging.getLogger(__name__)

REQUEST_COOLDOWN_HOURS = 72
REQUEST_EXPIRY_HOURS = 72
ACCEPTANCE_EXPIRY_HOURS = 24
DONOR_COOLDOWN_DAYS = 90


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
        verification_code=code,
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

def list_my_requests(
    db: DbSession,
    actor: User,
    *,
    status_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    stmt = select(BloodRequest).where(BloodRequest.requester_id == actor.id)
    count_stmt = select(func.count(BloodRequest.id)).where(
        BloodRequest.requester_id == actor.id
    )

    if status_filter:
        stmt = stmt.where(BloodRequest.status == status_filter)
        count_stmt = count_stmt.where(BloodRequest.status == status_filter)

    stmt = stmt.order_by(BloodRequest.created_at.desc()).limit(limit).offset(offset)

    rows = list(db.scalars(stmt))
    total = db.scalar(count_stmt) or 0

    requests = []
    for req in rows:
        requests.append({
            "id": req.id,
            "reference_code": req.reference_code,
            "blood_type_needed": req.blood_type_needed,
            "donors_needed": req.donors_needed,
            "accepted_count": req.accepted_count,
            "confirmed_count": req.confirmed_count,
            "donors_left": req.donors_needed - req.accepted_count,
            "urgency": req.urgency,
            "status": req.status,
            "notes": req.notes,
            "expires_at": req.expires_at,
            "created_at": req.created_at,
            "closed_at": req.closed_at,
            "hospital": {
                "id": req.hospital.id,
                "name": req.hospital.name,
                "address": req.hospital.address,
                "lga_name": req.hospital.lga.name,
                "state_name": req.hospital.state.name,
                "phone": req.hospital.phone,
            },
        })

    return {"requests": requests, "total": total, "limit": limit, "offset": offset}

def get_request_detail(db: DbSession, actor: User, request_id: uuid.UUID) -> dict:
    request = db.get(BloodRequest, request_id)
    if request is None:
        raise HTTPException(404, "Request not found")

    # Only the requester can see detail (for v1)
    if request.requester_id != actor.id:
        raise HTTPException(403, "You can only view your own requests")

    acceptances = list(
        db.scalars(
            select(DonorAcceptance)
            .where(DonorAcceptance.request_id == request_id)
            .order_by(DonorAcceptance.accepted_at.desc())
        )
    )

    return {
        "id": request.id,
        "reference_code": request.reference_code,
        "blood_type_needed": request.blood_type_needed,
        "donors_needed": request.donors_needed,
        "accepted_count": request.accepted_count,
        "confirmed_count": request.confirmed_count,
        "donors_left": request.donors_needed - request.accepted_count,
        "urgency": request.urgency,
        "status": request.status,
        "notes": request.notes,
        "expires_at": request.expires_at,
        "created_at": request.created_at,
        "closed_at": request.closed_at,
        "hospital": {
            "id": request.hospital.id,
            "name": request.hospital.name,
            "address": request.hospital.address,
            "lga_name": request.hospital.lga.name,
            "state_name": request.hospital.state.name,
            "phone": request.hospital.phone,
        },
        "acceptances": [
            {
                "id": a.id,
                "status": a.status,
                "accepted_at": a.accepted_at,
                "confirmed_at": a.confirmed_at,
            }
            for a in acceptances
        ],
    }

def confirm_donation(
    db: DbSession,
    actor: User,
    request_id: uuid.UUID,
    code: str,
) -> dict:
    now = datetime.now(UTC)

    # Lock the request
    request = db.scalar(
        select(BloodRequest)
        .where(BloodRequest.id == request_id)
        .with_for_update()
    )
    if request is None:
        raise HTTPException(404, "Request not found")

    if request.requester_id != actor.id:
        raise HTTPException(403, "Only the requester can confirm donations")

    if request.status not in ("open", "partial"):
        raise HTTPException(400, "This request is already closed")

    # Find the matching acceptance
    code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
    acceptance = db.scalar(
        select(DonorAcceptance)
        .where(
            DonorAcceptance.request_id == request_id,
            DonorAcceptance.verification_code_hash == code_hash,
        )
        .with_for_update()
    )

    if acceptance is None:
        add_audit_log(
            db,
            "acceptance.confirm_failed",
            actor_user_id=actor.id,
            target_type="blood_request",
            target_id=str(request_id),
            details={"reason": "invalid_code"},
        )
        db.commit()
        raise HTTPException(400, "Invalid verification code")

    if acceptance.status == "confirmed":
        raise HTTPException(400, "This code has already been used")

    if acceptance.status != "accepted":
        raise HTTPException(400, "This acceptance is no longer valid")

    if acceptance.expires_at <= now:
        raise HTTPException(400, "This acceptance has expired")

    # Mark confirmed
    acceptance.status = "confirmed"
    acceptance.confirmed_at = now
    acceptance.confirmed_by = actor.id

    request.confirmed_count += 1

    # Set donor's last donation date + cooldown
    donor = db.get(DonorProfile, acceptance.donor_id)
    if donor is not None:
        donor.last_donation_date = now.date()

    # Check if request is now fulfilled
    if request.confirmed_count >= request.donors_needed:
        request.status = "fulfilled"
        request.closed_at = now

        # Cancel other pending acceptances
        pending = db.scalars(
            select(DonorAcceptance).where(
                DonorAcceptance.request_id == request_id,
                DonorAcceptance.status == "accepted",
            )
        ).all()
        for p in pending:
            p.status = "cancelled"
            p.cancelled_at = now

    add_audit_log(
        db,
        "acceptance.confirmed",
        actor_user_id=actor.id,
        target_type="blood_request",
        target_id=str(request_id),
        details={
            "reference_code": request.reference_code,
            "confirmed_count": request.confirmed_count,
        },
    )
    db.commit()
    db.refresh(request)

    return {
        "status": "confirmed",
        "confirmed_count": request.confirmed_count,
        "donors_needed": request.donors_needed,
        "request_status": request.status,
        "message": (
            "Request fulfilled. Thank you."
            if request.status == "fulfilled"
            else f"{request.donors_needed - request.confirmed_count} more donor(s) needed."
        ),
    }

# =========================================================
# 1. Donor: list my acceptances
# =========================================================

def list_my_acceptances(db: DbSession, actor: User) -> dict:
    """Return the donor's acceptances, newest first."""
    rows = list(
        db.scalars(
            select(DonorAcceptance)
            .where(DonorAcceptance.donor_id == actor.id)
            .order_by(DonorAcceptance.accepted_at.desc())
        )
    )

    items = []
    for a in rows:
        req = db.get(BloodRequest, a.request_id)
        if req is None:
            continue

        # Only return the code if the acceptance is still active
        code = a.verification_code if a.status == "accepted" else None

        items.append({
            "id": a.id,
            "request_id": a.request_id,
            "reference_code": req.reference_code,
            "blood_type_needed": req.blood_type_needed,
            "urgency": req.urgency,
            "status": a.status,
            "verification_code": code,
            "accepted_at": a.accepted_at,
            "expires_at": a.expires_at,
            "confirmed_at": a.confirmed_at,
            "hospital": {
                "id": req.hospital.id,
                "name": req.hospital.name,
                "address": req.hospital.address,
                "lga_name": req.hospital.lga.name,
                "state_name": req.hospital.state.name,
                "phone": req.hospital.phone,
            },
        })

    return {"acceptances": items, "total": len(items)}


# =========================================================
# 2. Donor: cancel my acceptance
# =========================================================

def cancel_acceptance(db: DbSession, actor: User, acceptance_id: uuid.UUID) -> dict:
    now = datetime.now(UTC)

    acceptance = db.scalar(
        select(DonorAcceptance)
        .where(DonorAcceptance.id == acceptance_id)
        .with_for_update()
    )
    if acceptance is None:
        raise HTTPException(404, "Acceptance not found")

    if acceptance.donor_id != actor.id:
        raise HTTPException(403, "You can only cancel your own acceptances")

    if acceptance.status != "accepted":
        raise HTTPException(400, f"Cannot cancel a {acceptance.status} acceptance")

    # Lock the request too
    request = db.scalar(
        select(BloodRequest)
        .where(BloodRequest.id == acceptance.request_id)
        .with_for_update()
    )

    acceptance.status = "cancelled"
    acceptance.cancelled_at = now

    if request is not None:
        request.accepted_count = max(0, request.accepted_count - 1)

    add_audit_log(
        db,
        "acceptance.cancelled",
        actor_user_id=actor.id,
        target_type="acceptance",
        target_id=str(acceptance.id),
    )
    db.commit()

    return {"status": "cancelled", "message": "Your acceptance has been cancelled."}


# =========================================================
# 3. Requester: cancel my request
# =========================================================

def cancel_request(db: DbSession, actor: User, request_id: uuid.UUID) -> None:
    now = datetime.now(UTC)

    request = db.scalar(
        select(BloodRequest)
        .where(BloodRequest.id == request_id)
        .with_for_update()
    )
    if request is None:
        raise HTTPException(404, "Request not found")

    if request.requester_id != actor.id:
        raise HTTPException(403, "You can only cancel your own requests")

    if request.status not in ("open", "partial"):
        raise HTTPException(400, f"Cannot cancel a {request.status} request")

    request.status = "cancelled"
    request.closed_at = now

    # Cancel all pending acceptances
    pending = db.scalars(
        select(DonorAcceptance).where(
            DonorAcceptance.request_id == request_id,
            DonorAcceptance.status == "accepted",
        )
    ).all()
    for p in pending:
        p.status = "cancelled"
        p.cancelled_at = now

    add_audit_log(
        db,
        "request.cancelled",
        actor_user_id=actor.id,
        target_type="blood_request",
        target_id=str(request_id),
        details={"reference_code": request.reference_code},
    )
    db.commit()


# =========================================================
# 4. Donor: update my profile
# =========================================================

def update_donor_profile(
    db: DbSession,
    actor: User,
    payload: "DonorUpdateRequest",
) -> dict:
    from app.modules.donors.service import get_donor_profile

    profile = db.get(DonorProfile, actor.id)
    if profile is None:
        raise HTTPException(404, "You are not registered as a donor")

    updates = payload.model_dump(exclude_unset=True)

    # Validate location if either state_id or lga_id is being changed
    if "state_id" in updates or "lga_id" in updates:
        new_state_id = updates.get("state_id", profile.state_id)
        new_lga_id = updates.get("lga_id", profile.lga_id)

        state = db.get(State, new_state_id)
        if state is None:
            raise HTTPException(422, "Unknown state")

        lga = db.get(Lga, new_lga_id)
        if lga is None or lga.state_id != state.id:
            raise HTTPException(422, f"LGA does not belong to {state.name}")

    for key, value in updates.items():
        setattr(profile, key, value)

    db.commit()
    db.refresh(profile)

    return get_donor_profile(db, actor)