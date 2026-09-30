import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------- Community Admin: view own community ----------

class CommunityMeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    type: str
    state_id: uuid.UUID
    lga_id: uuid.UUID
    state_name: str
    lga_name: str
    status: str
    member_count: int
    pending_count: int
    created_at: datetime


# ---------- Targeted email invite ----------

class InviteMemberRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr


class MemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    community_id: uuid.UUID
    user_id: uuid.UUID | None
    full_name: str
    email: EmailStr
    phone: str | None
    method: str
    status: str
    rejection_reason: str | None
    joined_at: datetime | None
    created_at: datetime


class MemberListResponse(BaseModel):
    members: list[MemberResponse]
    total: int
    limit: int
    offset: int


# ---------- Approve / Reject ----------
class RejectMemberRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


# ---------- Join link ----------

class JoinLinkResponse(BaseModel):
    code: str
    url: str
    is_active: bool
    expires_at: datetime | None
    created_at: datetime


class JoinLinkPublicPreview(BaseModel):
    community_name: str
    community_type: str
    state_name: str
    lga_name: str
    is_open: bool


class JoinApplicationRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    phone: str = Field(min_length=7, max_length=32)


class JoinApplicationResponse(BaseModel):
    status: Literal["pending"] = "pending"
    message: str = "Your application has been submitted. You'll be notified when it's reviewed."


# ---------- Public: accept member invite ----------
class MemberInviteAcceptRequest(BaseModel):
    password: str = Field(min_length=8, max_length=128)
    phone: str = Field(min_length=7, max_length=32)



class MemberInviteAcceptResponse(BaseModel):
    status: str = "accepted"
    user_id: uuid.UUID
    community_id: uuid.UUID

# ---------- Public: view member invite (prefill) ----------

class MemberInviteDetailsResponse(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    community_name: str
    community_type: str
    invited_by_name: str
    expires_at: datetime
    is_expired: bool
    is_used: bool