import uuid
from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BloodType(str, Enum):
    A_pos = "A+"
    A_neg = "A-"
    B_pos = "B+"
    B_neg = "B-"
    AB_pos = "AB+"
    AB_neg = "AB-"
    O_pos = "O+"
    O_neg = "O-"


class Genotype(str, Enum):
    AA = "AA"
    AS = "AS"
    AC = "AC"
    SS = "SS"
    SC = "SC"


class CompleteDonorProfileRequest(BaseModel):
    """All fields required except latitude/longitude."""

    blood_type: BloodType = Field(
        description="Blood group. One of: A+, A-, B+, B-, AB+, AB-, O+, O-"
    )
    genotype: Genotype = Field(
        description="Genotype. One of: AA, AS, AC, SS, SC"
    )
    state_id: uuid.UUID = Field(description="Nigerian state UUID")
    lga_id: uuid.UUID = Field(
        description="LGA UUID that belongs to the selected state"
    )
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @field_validator("blood_type", "genotype", mode="before")
    @classmethod
    def reject_empty(cls, v):
        if v is None or (isinstance(v, str) and not v.strip()):
            raise ValueError("This field is required and cannot be empty")
        return v


class DonorProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    profile_id: uuid.UUID
    blood_type: str
    is_genotype_eligible: bool
    state_id: uuid.UUID
    lga_id: uuid.UUID
    state_name: str
    lga_name: str
    latitude: float | None
    longitude: float | None
    availability: bool
    last_donation_date: date | None
    is_eligible: bool
    eligible_at: datetime | None
    created_at: datetime