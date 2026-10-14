import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.enums import UserStatus


class RoleInfo(BaseModel):
    name: str
    description: str | None


class UserListItem(BaseModel):
    id: uuid.UUID
    user_code: str
    email: EmailStr
    first_name: str
    last_name: str
    phone: str | None
    status: UserStatus
    email_verified_at: datetime | None
    last_login_at: datetime | None
    created_at: datetime
    roles: list[str]
    is_donor: bool
    is_member: bool


class UsersListResponse(BaseModel):
    users: list[UserListItem]
    total: int
    limit: int
    offset: int


class UserDetailResponse(BaseModel):
    id: uuid.UUID
    user_code: str
    email: EmailStr
    first_name: str
    last_name: str
    phone: str | None
    status: UserStatus
    email_verified_at: datetime | None
    last_login_at: datetime | None
    failed_login_attempts: int
    locked_until: datetime | None
    created_at: datetime
    updated_at: datetime
    roles: list[RoleInfo]
    is_donor: bool
    is_member: bool
    donor_profile: dict | None
    community_membership: dict | None


class UpdateUserStatusRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class UpdateUserStatusResponse(BaseModel):
    status: str
    user_id: uuid.UUID
    new_status: UserStatus
    message: str