import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


# =========================================================
# List
# =========================================================

class HospitalBrief(BaseModel):
    id: uuid.UUID
    name: str
    lga_name: str
    state_name: str


class CommunityBrief(BaseModel):
    id: uuid.UUID
    name: str


class AdminRequestListItem(BaseModel):
    id: uuid.UUID
    reference_code: str
    blood_type_needed: str
    donors_needed: int
    accepted_count: int
    confirmed_count: int
    status: str
    urgency: str
    hospital: HospitalBrief
    community: CommunityBrief
    created_at: datetime


class AdminRequestsListResponse(BaseModel):
    requests: list[AdminRequestListItem]
    limit: int
    offset: int


# =========================================================
# Detail
# =========================================================

class HospitalDetail(BaseModel):
    id: uuid.UUID
    name: str
    address: str
    lga_name: str
    state_name: str
    phone: str


class RequesterInfo(BaseModel):
    id: uuid.UUID
    full_name: str
    phone: str | None
    email: EmailStr
    role: str


class CommunityDetail(BaseModel):
    id: uuid.UUID
    name: str
    type: str
    state_name: str


class DonorSlot(BaseModel):
    slot: int
    status: str
    confirmed_at: datetime | None


class AdminRequestDetailResponse(BaseModel):
    id: uuid.UUID
    reference_code: str
    status: str
    blood_type_needed: str
    donors_needed: int
    accepted_count: int
    confirmed_count: int
    donors_left: int
    urgency: str
    notes: str | None
    created_at: datetime
    expires_at: datetime
    closed_at: datetime | None
    hospital: HospitalDetail
    requester: RequesterInfo
    community: CommunityDetail
    donor_slots: list[DonorSlot]