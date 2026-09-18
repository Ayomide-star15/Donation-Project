import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.enums import UserStatus


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginResponse(BaseModel):
    status: Literal["authenticated", "otp_required"]
    challenge_id: uuid.UUID | None = None
    expires_in: int | None = None
    masked_email: str | None = None


class OtpVerifyRequest(BaseModel):
    challenge_id: uuid.UUID
    code: str = Field(pattern=r"^\d{6}$")


class OtpResendRequest(BaseModel):
    challenge_id: uuid.UUID


class OtpChallengeResponse(BaseModel):
    status: Literal["otp_required"] = "otp_required"
    challenge_id: uuid.UUID
    expires_in: int
    resend_after: int
    masked_email: str


class AuthenticatedResponse(BaseModel):
    status: Literal["authenticated"] = "authenticated"


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_code: str
    email: EmailStr
    first_name: str
    last_name: str
    status: UserStatus
    email_verified_at: datetime | None
    last_login_at: datetime | None
    created_at: datetime


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    auth_level: str
    device_name: str | None
    ip_address: str | None
    user_agent: str | None
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    idle_expires_at: datetime | None
