import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session as DbSession

from app.core.database import get_db
from app.modules.admin import community_service
from app.modules.admin.community_schemas import (
    CommunitiesListResponse,
    CommunityDetailResponse,
)
from app.modules.auth.dependencies import AuthContext, require_super_admin


router = APIRouter(prefix="/admin/communities", tags=["super admin: communities"])


@router.get("", response_model=CommunitiesListResponse)
def list_communities(
    context: AuthContext = Depends(require_super_admin),
    db: DbSession = Depends(get_db),
    status_filter: str | None = Query(default=None, alias="status"),
    activity: str | None = Query(default=None),
    state: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """List all communities with member counts + activity level."""
    return community_service.list_communities(
        db,
        status_filter=status_filter,
        activity_filter=activity,
        state_filter=state,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get("/{community_id}", response_model=CommunityDetailResponse)
def get_community_detail(
    community_id: uuid.UUID,
    context: AuthContext = Depends(require_super_admin),
    db: DbSession = Depends(get_db),
) -> dict:
    """View one community in detail."""
    return community_service.get_community_detail(db, community_id)