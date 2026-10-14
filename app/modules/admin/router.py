import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session as DbSession

from app.core.database import get_db
from app.core.enums import UserStatus
from app.modules.admin import service
from app.modules.admin.schemas import (
    UpdateUserStatusRequest,
    UpdateUserStatusResponse,
    UserDetailResponse,
    UsersListResponse,
)
from app.modules.auth.dependencies import AuthContext, require_super_admin


router = APIRouter(prefix="/admin", tags=["super admin: users"])


@router.get("/users", response_model=UsersListResponse)
def list_users(
    context: AuthContext = Depends(require_super_admin),
    db: DbSession = Depends(get_db),
    status_filter: UserStatus | None = Query(default=None, alias="status"),
    role: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """List all users, filterable by status, role, and search."""
    return service.list_users(
        db,
        status_filter=status_filter,
        role_filter=role,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get("/users/{user_id}", response_model=UserDetailResponse)
def get_user_detail(
    user_id: uuid.UUID,
    context: AuthContext = Depends(require_super_admin),
    db: DbSession = Depends(get_db),
) -> dict:
    """Full user detail: roles, donor profile, community membership."""
    return service.get_user_detail(db, user_id)


@router.post(
    "/users/{user_id}/suspend",
    response_model=UpdateUserStatusResponse,
)
def suspend_user(
    user_id: uuid.UUID,
    payload: UpdateUserStatusRequest | None = None,
    context: AuthContext = Depends(require_super_admin),
    db: DbSession = Depends(get_db),
) -> dict:
    """Suspend a user. Revokes all their sessions."""
    return service.suspend_user(
        db, context.user, user_id, payload.reason if payload else None
    )


@router.post(
    "/users/{user_id}/ban",
    response_model=UpdateUserStatusResponse,
)
def ban_user(
    user_id: uuid.UUID,
    payload: UpdateUserStatusRequest | None = None,
    context: AuthContext = Depends(require_super_admin),
    db: DbSession = Depends(get_db),
) -> dict:
    """Ban a user. Revokes all their sessions."""
    return service.ban_user(
        db, context.user, user_id, payload.reason if payload else None
    )


@router.post(
    "/users/{user_id}/reactivate",
    response_model=UpdateUserStatusResponse,
)
def reactivate_user(
    user_id: uuid.UUID,
    payload: UpdateUserStatusRequest | None = None,
    context: AuthContext = Depends(require_super_admin),
    db: DbSession = Depends(get_db),
) -> dict:
    """Reactivate a suspended, banned, or disabled user."""
    return service.reactivate_user(
        db, context.user, user_id, payload.reason if payload else None
    )