import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class HospitalCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    phone: str = Field(min_length=7, max_length=32)
    address: str = Field(min_length=5, max_length=500)
    state_id: uuid.UUID
    lga_id: uuid.UUID
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class HospitalUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    phone: str | None = Field(default=None, min_length=7, max_length=32)
    address: str | None = Field(default=None, min_length=5, max_length=500)
    state_id: uuid.UUID | None = None
    lga_id: uuid.UUID | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    is_active: bool | None = None


class HospitalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    phone: str
    address: str
    state_id: uuid.UUID
    lga_id: uuid.UUID
    state_name: str
    lga_name: str
    latitude: float | None
    longitude: float | None
    is_active: bool
    created_at: datetime