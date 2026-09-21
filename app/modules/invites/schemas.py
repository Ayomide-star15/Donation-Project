import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class InviteCreateRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    community_name: str = Field(min_length=2, max_length=200)


class InviteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    first_name: str
    last_name: str
    community_name: str
    status: str
    expires_at: datetime
    created_at: datetime