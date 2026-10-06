from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session as DbSession

from app.core.database import get_db
from app.modules.auth.dependencies import AuthContext, get_auth_context
from app.modules.auth.service import complete_donor_profile
from app.modules.donors import service
from app.modules.donors.schemas import (
    CompleteDonorProfileRequest,
    DonorProfileResponse,
)


router = APIRouter(prefix="/donors", tags=["donors"])


@router.post(
    "/profile",
    response_model=DonorProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_donor_profile(
    payload: CompleteDonorProfileRequest,
    context: AuthContext = Depends(get_auth_context),
    db: DbSession = Depends(get_db),
) -> dict:
    complete_donor_profile(db, context.user, payload)
    return service.get_donor_profile(db, context.user)


@router.get("/me", response_model=DonorProfileResponse)
def get_my_donor_profile(
    context: AuthContext = Depends(get_auth_context),
    db: DbSession = Depends(get_db),
) -> dict:
    return service.get_donor_profile(db, context.user)