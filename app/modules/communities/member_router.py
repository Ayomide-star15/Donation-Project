import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session as DbSession

from app.core.config import settings
from app.core.database import get_db
from app.modules.auth.dependencies import AuthContext, get_auth_context
from app.modules.communities import member_service
from app.modules.communities.member_schemas import (
    CommunityMeResponse,
    InviteMemberRequest,
    JoinLinkResponse,
    MemberListResponse,
    MemberResponse,
    RejectMemberRequest,
)
from app.modules.notifications.email import EmailService, get_email_service


router = APIRouter(prefix="/community", tags=["community"])


@router.get("/me", response_model=CommunityMeResponse)
def get_my_community(
    context: AuthContext = Depends(get_auth_context),
    db: DbSession = Depends(get_db),
):
    return member_service.get_my_community(db, context.user)


@router.post(
    "/members/invite",
    response_model=MemberResponse,
    status_code=status.HTTP_201_CREATED,
)
def invite_member(
    payload: InviteMemberRequest,
    context: AuthContext = Depends(get_auth_context),
    db: DbSession = Depends(get_db),
    email_service: EmailService = Depends(get_email_service),
):
    return member_service.invite_member(
        db, email_service, context.user, payload.full_name, str(payload.email)
    )


@router.get("/members", response_model=MemberListResponse)
def list_members(
    context: AuthContext = Depends(get_auth_context),
    db: DbSession = Depends(get_db),
    status_filter: str | None = Query(default=None, alias="status"),
    method: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
):
    return member_service.list_members(
        db,
        context.user,
        status_filter=status_filter,
        method_filter=method,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get("/members/{member_id}", response_model=MemberResponse)
def get_member(
    member_id: uuid.UUID,
    context: AuthContext = Depends(get_auth_context),
    db: DbSession = Depends(get_db),
):
    return member_service.get_member(db, context.user, member_id)


@router.delete("/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_member(
    member_id: uuid.UUID,
    context: AuthContext = Depends(get_auth_context),
    db: DbSession = Depends(get_db),
):
    member_service.revoke_member(db, context.user, member_id)


@router.post("/members/{member_id}/approve", response_model=MemberResponse)
def approve_member(
    member_id: uuid.UUID,
    context: AuthContext = Depends(get_auth_context),
    db: DbSession = Depends(get_db),
):
    return member_service.approve_member(db, context.user, member_id)


@router.post("/members/{member_id}/reject", response_model=MemberResponse)
def reject_member(
    member_id: uuid.UUID,
    payload: RejectMemberRequest | None = None,
    context: AuthContext = Depends(get_auth_context),
    db: DbSession = Depends(get_db),
):
    return member_service.reject_member(
        db, context.user, member_id, payload.reason if payload else None
    )


# ---------- Join link ----------

def _join_link_response(link) -> dict:
    return {
        "code": link.code,
        "url": f"{settings.FRONTEND_URL.rstrip('/')}/join/{link.code}",
        "is_active": link.is_active,
        "created_at": link.created_at,
    }


@router.post(
    "/join-link",
    response_model=JoinLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_join_link(
    context: AuthContext = Depends(get_auth_context),
    db: DbSession = Depends(get_db),
):
    return _join_link_response(member_service.generate_join_link(db, context.user))


@router.get("/join-link", response_model=JoinLinkResponse)
def get_join_link(
    context: AuthContext = Depends(get_auth_context),
    db: DbSession = Depends(get_db),
):
    return _join_link_response(member_service.get_join_link(db, context.user))


@router.delete("/join-link", status_code=status.HTTP_204_NO_CONTENT)
def revoke_join_link(
    context: AuthContext = Depends(get_auth_context),
    db: DbSession = Depends(get_db),
):
    member_service.revoke_join_link(db, context.user)