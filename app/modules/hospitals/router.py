import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session as DbSession

from app.core.database import get_db
from app.modules.auth.dependencies import AuthContext, require_super_admin
from app.modules.hospitals import service
from app.modules.hospitals.schemas import (
    HospitalCreate,
    HospitalResponse,
    HospitalUpdate,
)


admin_router = APIRouter(prefix="/admin/hospitals", tags=["admin:hospitals"])
public_router = APIRouter(prefix="/hospitals", tags=["hospitals"])


@admin_router.post("", response_model=HospitalResponse, status_code=status.HTTP_201_CREATED)
def create_hospital(
    payload: HospitalCreate,
    context: AuthContext = Depends(require_super_admin),
    db: DbSession = Depends(get_db),
) -> dict:
    return service.create_hospital(db, payload, context.user)


@admin_router.get("", response_model=list[HospitalResponse])
def list_hospitals_admin(
    context: AuthContext = Depends(require_super_admin),
    db: DbSession = Depends(get_db),
    state_id: uuid.UUID | None = Query(default=None),
    lga_id: uuid.UUID | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    return service.list_hospitals(
        db,
        state_id=state_id,
        lga_id=lga_id,
        is_active=is_active,
        limit=limit,
        offset=offset,
    )


@admin_router.patch("/{hospital_id}", response_model=HospitalResponse)
def update_hospital(
    hospital_id: uuid.UUID,
    payload: HospitalUpdate,
    context: AuthContext = Depends(require_super_admin),
    db: DbSession = Depends(get_db),
) -> dict:
    return service.update_hospital(db, hospital_id, payload, context.user)


@admin_router.delete("/{hospital_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_hospital(
    hospital_id: uuid.UUID,
    context: AuthContext = Depends(require_super_admin),
    db: DbSession = Depends(get_db),
) -> None:
    service.deactivate_hospital(db, hospital_id, context.user)


@public_router.get("", response_model=list[HospitalResponse])
def list_hospitals_public(
    db: DbSession = Depends(get_db),
    state_id: uuid.UUID | None = Query(default=None),
    lga_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=200, le=500),
) -> list[dict]:
    return service.list_hospitals(
        db, state_id=state_id, lga_id=lga_id, is_active=True, limit=limit
    )