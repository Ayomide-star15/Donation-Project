import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CommunityType(str, Enum):
    hospital = "hospital"
    university = "university"
    workplace = "workplace"
    ngo = "ngo"
    religious = "religious"
    government = "government"
    cooperative = "cooperative"
    other = "other"


class InviteDetailsResponse(BaseModel):
    """Public — shown on the accept page. Prefills both screens."""

    first_name: str
    last_name: str
    email: EmailStr
    community_name: str
    invited_by_name: str
    expires_at: datetime
    is_expired: bool
    is_used: bool


class AcceptInviteRequest(BaseModel):
    """Final submit — combines Screen 1 + Screen 2."""

    # Screen 1 — typed by the invitee
    password: str = Field(min_length=8, max_length=128)
    phone: str | None = Field(default=None, max_length=32)

    # Screen 2 — community profile
    community_type: CommunityType
    state_id: uuid.UUID
    lga_id: uuid.UUID


class CommunityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    type: str
    state_id: uuid.UUID
    lga_id: uuid.UUID
    state_name: str
    lga_name: str
    status: str
    created_at: datetime


class AcceptInviteResponse(BaseModel):
    status: str = "accepted"
    user_id: uuid.UUID
    community: CommunityResponse


class AdminSummaryResponse(BaseModel):
    """Optional — for showing 'You're now admin of X' after accept."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    community_id: uuid.UUID
    user_id: uuid.UUID
    status: str
    created_at: datetime