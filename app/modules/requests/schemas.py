import uuid
from datetime import datetime
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


class Urgency(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class CreateRequestPayload(BaseModel):
    blood_type_needed: BloodType = Field(
        description="Blood type needed: A+, A-, B+, B-, AB+, AB-, O+, O-"
    )
    donors_needed: int = Field(
        ge=1, le=10,
        description="How many donors needed (1-10). Above 10 requires override.",
    )
    hospital_id: uuid.UUID = Field(
        description="Hospital where blood is needed"
    )
    urgency: Urgency = Field(default=Urgency.medium)
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("blood_type_needed", "hospital_id", mode="before")
    @classmethod
    def reject_empty(cls, v):
        if v is None or (isinstance(v, str) and not v.strip()):
            raise ValueError("This field is required")
        return v


class HospitalSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    address: str
    state_name: str
    lga_name: str
    phone: str


class RequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reference_code: str
    blood_type_needed: str
    donors_needed: int
    urgency: str
    notes: str | None
    status: str
    accepted_count: int
    confirmed_count: int
    requester_cooldown_until: datetime
    expires_at: datetime
    created_at: datetime
    hospital: HospitalSummary