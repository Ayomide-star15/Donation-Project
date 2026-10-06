from datetime import UTC, datetime, time, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session as DbSession

from app.modules.donors.models import DonorProfile
from app.modules.users.models import User


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