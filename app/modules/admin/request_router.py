import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session as DbSession

from app.core.database import get_db
from app.modules.admin import request_service
from app.modules.admin.request_schemas import (
    AdminRequestDetailResponse,
    AdminRequestsListResponse,
)
from app.modules.auth.dependencies import AuthContext, require_super_admin


router = APIRouter(prefix="/admin/requests", tags=["super admin: requests"])


@router.get("", response_model=AdminRequestsListResponse)
def list_requests(
    context: AuthContext = Depends(require_super_admin),
    db: DbSession = Depends(get_db),
    status_filter: str | None = Query(default=None, alias="status"),
    urgency: str | None = Query(default=None),
    blood_type: str | None = Query(default=None),
    community_id: uuid.UUID | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """List all blood requests platform-wide, filterable."""
    return request_service.list_requests(
        db,
        status_filter=status_filter,
        urgency_filter=urgency,
        blood_type_filter=blood_type,
        community_id=community_id,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get("/{request_id}", response_model=AdminRequestDetailResponse)
def get_request_detail(
    request_id: uuid.UUID,
    context: AuthContext = Depends(require_super_admin),
    db: DbSession = Depends(get_db),
) -> dict:
    """View one request in detail — no donor identities exposed."""
    return request_service.get_request_detail(db, request_id)