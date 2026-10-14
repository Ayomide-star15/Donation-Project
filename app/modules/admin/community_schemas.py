import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class CommunityAdminInfo(BaseModel):
    id: uuid.UUID
    full_name: str
    email: EmailStr


class CommunityListItem(BaseModel):
    id: uuid.UUID
    name: str
    type: str
    state_name: str
    lga_name: str
    status: str
    admin: CommunityAdminInfo | None
    member_count: int
    activity_level: str  # "high" | "medium" | "low"
    created_at: datetime


class CommunitiesListResponse(BaseModel):
    communities: list[CommunityListItem]
    total: int
    limit: int
    offset: int


class CommunityStats(BaseModel):
    member_count: int
    total_requests: int
    fulfilled_requests: int
    open_requests: int


class RecentRequestItem(BaseModel):
    id: uuid.UUID
    reference_code: str
    blood_type_needed: str
    status: str
    created_at: datetime


class CommunityDetailResponse(BaseModel):
    id: uuid.UUID
    name: str
    type: str
    state_name: str
    lga_name: str
    status: str
    created_at: datetime
    updated_at: datetime

    stats: CommunityStats
    admin: CommunityAdminInfo | None
    recent_requests: list[RecentRequestItem]