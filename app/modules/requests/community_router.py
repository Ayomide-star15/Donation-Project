import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session as DbSession

from app.core.database import get_db
from app.modules.auth.dependencies import AuthContext, get_auth_context
from app.modules.requests import service
from app.modules.requests.schemas import (
    CommunityRequestDetailResponse,
    CommunityRequestsListResponse,
)


router = APIRouter(prefix="/community/requests", tags=["community admin"])


@router.get("", response_model=CommunityRequestsListResponse)
def list_community_requests(
    context: AuthContext = Depends(get_auth_context),
    db: DbSession = Depends(get_db),
    status_filter: str | None = Query(default=None, alias="status"),
    urgency: str | None = Query(default=None),
    blood_type: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """List all blood requests raised by my community's members."""
    return service.list_community_requests(
        db,
        context.user,
        status_filter=status_filter,
        urgency_filter=urgency,
        blood_type_filter=blood_type,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get("/{request_id}", response_model=CommunityRequestDetailResponse)
def get_community_request_detail(
    request_id: uuid.UUID,
    context: AuthContext = Depends(get_auth_context),
    db: DbSession = Depends(get_db),
) -> dict:
    """View a single request from my community in detail."""
    return service.get_community_request_detail(db, context.user, request_id)