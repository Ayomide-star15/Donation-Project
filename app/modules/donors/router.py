import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session as DbSession

from app.core.database import get_db
from app.modules.auth.dependencies import AuthContext, get_auth_context
from app.modules.auth.service import complete_donor_profile
from app.modules.donors import service
from app.modules.requests import service as requests_service
from app.modules.donors.schemas import (
    CompleteDonorProfileRequest,
    DonorProfileResponse,
    DonorFeedResponse,
    DonorUpdateRequest,
)

from app.modules.requests.schemas import (
    AcceptRequestResponse,
    MyAcceptancesResponse,
    CancelAcceptanceResponse,
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

@router.get("/requests", response_model=DonorFeedResponse)
def get_donor_feed(
    context: AuthContext = Depends(get_auth_context),
    db: DbSession = Depends(get_db),
) -> dict:
    """Feed of open requests this donor can help with."""
    return service.get_donor_feed(db, context.user)

@router.post(
    "/{request_id}/accept",
    response_model=AcceptRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def accept_request(
    request_id: uuid.UUID,
    context: AuthContext = Depends(get_auth_context),
    db: DbSession = Depends(get_db),
) -> dict:
    """Donor accepts a request, receives a verification code."""
    return service.accept_request(db, context.user, request_id)


@router.get("/acceptances", response_model=MyAcceptancesResponse)
def list_my_acceptances(
    context: AuthContext = Depends(get_auth_context),
    db: DbSession = Depends(get_db),
) -> dict:
    """List my acceptances with verification codes."""
    return requests_service.list_my_acceptances(db, context.user)


@router.post(
    "/acceptances/{acceptance_id}/cancel",
    response_model=CancelAcceptanceResponse,
)
def cancel_acceptance(
    acceptance_id: uuid.UUID,
    context: AuthContext = Depends(get_auth_context),
    db: DbSession = Depends(get_db),
) -> dict:
    """Cancel one of my acceptances."""
    return requests_service.cancel_acceptance(db, context.user, acceptance_id)


@router.patch("/me", response_model=DonorProfileResponse)
def update_donor_profile(
    payload: DonorUpdateRequest,
    context: AuthContext = Depends(get_auth_context),
    db: DbSession = Depends(get_db),
) -> dict:
    """Update my availability / location."""
    return requests_service.update_donor_profile(db, context.user, payload)