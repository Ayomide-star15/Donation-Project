import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.enums import UserStatus


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class LoginChallengeResponse(BaseModel):
    next_step: Literal["mfa_setup", "mfa_verify"]
    challenge_token: str


class MfaSetupRequest(BaseModel):
    challenge_token: str


class MfaSetupResponse(BaseModel):
    provisioning_uri: str


class MfaVerifyRequest(BaseModel):
    challenge_token: str
    code: str = Field(pattern=r"^\d{6}$")


class MfaRecoveryRequest(BaseModel):
    challenge_token: str
    recovery_code: str = Field(min_length=8, max_length=64)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    recovery_codes: list[str] | None = None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
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
    ip_address: str | None
    user_agent: str | None
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime
