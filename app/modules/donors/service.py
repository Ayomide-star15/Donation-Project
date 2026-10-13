from datetime import UTC, datetime, time, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session as DbSession
from sqlalchemy import or_, select
from app.modules.donors.models import DonorProfile
from app.modules.users.models import User
from app.modules.donors.compatibility import recipient_types_donor_can_help
from app.modules.requests.models import BloodRequest, BloodRequest
from app.modules.requests.sanitizer import sanitize_note

DONOR_COOLDOWN_DAYS = 90   # TODO: read from platform_settings

def _compute_eligibility(profile: DonorProfile) -> tuple[bool, datetime | None]:
    # Genotype ineligible → never eligible, no matter what
    if not profile.is_genotype_eligible:
        return False, None

    if profile.last_donation_date is None:
        return True, None

    eligible_at = datetime.combine(
        profile.last_donation_date + timedelta(days=DONOR_COOLDOWN_DAYS),
        time.min,
        tzinfo=UTC,
    )
    return eligible_at <= datetime.now(UTC), eligible_at

def get_donor_profile(db: DbSession, user: User) -> dict:
    profile = db.get(DonorProfile, user.id)
    if profile is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "You are not registered as a donor",
        )

    is_eligible, eligible_at = _compute_eligibility(profile)

    return {
        "profile_id": profile.profile_id,
        "blood_type": profile.blood_type,
        "is_genotype_eligible": profile.is_genotype_eligible,
        "state_id": profile.state_id,
        "lga_id": profile.lga_id,
        "state_name": profile.state.name,
        "lga_name": profile.lga.name,
        "latitude": profile.latitude,
        "longitude": profile.longitude,
        "availability": profile.availability,
        "last_donation_date": profile.last_donation_date,
        "is_eligible": is_eligible,
        "eligible_at": eligible_at,
        "created_at": profile.created_at,
    }

def _donor_is_eligible(donor) -> bool:
    """Can this donor currently accept a request?"""
    if not donor.availability:
        return False
    if not donor.is_genotype_eligible:
        return False
    if donor.last_donation_date:
        eligible_on = donor.last_donation_date + timedelta(days=DONOR_COOLDOWN_DAYS)
        if eligible_on > datetime.now(UTC).date():
            return False
    return True


def _compute_match_tier(donor, request) -> int:
    """1 = best match. 5 = no match (exclude)."""
    hospital = request.hospital
    exact = donor.blood_type == request.blood_type_needed
    same_lga = donor.lga_id == hospital.lga_id
    same_state = donor.state_id == hospital.state_id

    if same_lga and exact:
        return 1
    if same_state and exact:
        return 2
    if same_lga and not exact:
        return 3
    if same_state and not exact:
        return 4
    return 5


def get_donor_feed(db, user) -> dict:
    """Open requests this donor can help with, sorted by best match."""
    donor = db.get(DonorProfile, user.id)
    if donor is None:
        raise HTTPException(
            status_code=403,
            detail="Only registered donors can access the request feed",
        )

    if not donor.is_genotype_eligible:
        return {"requests": [], "total": 0}

    now = datetime.now(UTC)
    recipient_types = recipient_types_donor_can_help(donor.blood_type)

    stmt = (
        select(BloodRequest)
        .where(
            BloodRequest.status.in_(["open", "partial"]),
            BloodRequest.blood_type_needed.in_(recipient_types),
            BloodRequest.expires_at > now,
            BloodRequest.accepted_count < BloodRequest.donors_needed,
            or_(
                BloodRequest.hospital.has(lga_id=donor.lga_id),
                BloodRequest.hospital.has(state_id=donor.state_id),
            ),
        )
    )

    candidates = list(db.scalars(stmt))

    scored = []
    for req in candidates:
        tier = _compute_match_tier(donor, req)
        if tier < 5:
            scored.append((tier, req.created_at, req))

    scored.sort(key=lambda x: (x[0], x[1]))

    donor_eligible = _donor_is_eligible(donor)

    result = []
    for tier, _, req in scored:
        result.append({
            "id": req.id,
            "reference_code": req.reference_code,
            "blood_type_needed": req.blood_type_needed,
            "donors_needed": req.donors_needed,
            "accepted_count": req.accepted_count,
            "confirmed_count": req.confirmed_count,
            "donors_left": req.donors_needed - req.accepted_count,
            "urgency": req.urgency,
            "status": req.status,
            "match_tier": tier,
            "note": sanitize_note(req.notes),
            "is_eligible": donor_eligible,
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
        })

    return {"requests": result, "total": len(result)}