import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session as DbSession
from fastapi import Query
from app.core.database import get_db
from app.modules.auth.dependencies import AuthContext, get_auth_context
from app.modules.requests import service
from app.modules.requests.schemas import (
    CreateRequestPayload, 
    RequestResponse,
    MyRequestsListResponse,
    RequestDetailResponse,
    ConfirmDonationRequest,
    ConfirmDonationResponse,
)
router = APIRouter(prefix="/requests", tags=["community member"])


@router.post(
    "",
    response_model=RequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_request(
    payload: CreateRequestPayload,
    context: AuthContext = Depends(get_auth_context),
    db: DbSession = Depends(get_db),
) -> dict:
    """Raise a blood request as an active community member."""
    return service.create_request(db, context.user, payload)

@router.get("/me", response_model=MyRequestsListResponse)
def list_my_requests(
    context: AuthContext = Depends(get_auth_context),
    db: DbSession = Depends(get_db),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    return service.list_my_requests(
        db, context.user,
        status_filter=status_filter, limit=limit, offset=offset,
    )


@router.get("/{request_id}", response_model=RequestDetailResponse)
def get_request_detail(
    request_id: uuid.UUID,
    context: AuthContext = Depends(get_auth_context),
    db: DbSession = Depends(get_db),
) -> dict:
    return service.get_request_detail(db, context.user, request_id)

@router.post("/{request_id}/confirm", response_model=ConfirmDonationResponse)
def confirm_donation(
    request_id: uuid.UUID,
    payload: ConfirmDonationRequest,
    context: AuthContext = Depends(get_auth_context),
    db: DbSession = Depends(get_db),
) -> dict:
    return service.confirm_donation(db, context.user, request_id, payload.code)