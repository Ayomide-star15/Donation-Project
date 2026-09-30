from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session as DbSession

from app.core.database import get_db
from app.modules.communities import member_service
from app.modules.communities.member_schemas import (
    JoinApplicationRequest,
    JoinApplicationResponse,
    JoinLinkPublicPreview,
    MemberInviteAcceptRequest,
    MemberInviteAcceptResponse,
    MemberInviteDetailsResponse,
)


router = APIRouter(tags=["public:join"])


@router.get("/join/{code}", response_model=JoinLinkPublicPreview)
def preview_join_link(code: str, db: DbSession = Depends(get_db)) -> dict:
    return member_service.preview_join_link(db, code)


@router.post(
    "/join/{code}",
    response_model=JoinApplicationResponse,
    status_code=status.HTTP_201_CREATED,
)
def apply_via_join_link(
    code: str,
    payload: JoinApplicationRequest,
    db: DbSession = Depends(get_db),
):
    member_service.apply_via_join_link(
        db,
        code,
        payload.full_name,
        str(payload.email),
        payload.password,
        payload.phone,
    )
    return JoinApplicationResponse()


@router.post(
    "/member-invites/{token}/accept",
    response_model=MemberInviteAcceptResponse,
    status_code=status.HTTP_201_CREATED,
)
def accept_member_invite(
    token: str,
    payload: MemberInviteAcceptRequest,
    db: DbSession = Depends(get_db),
):
    return member_service.accept_member_invite(
        db, token, payload.password, payload.phone
    )

@router.get("/member-invites/{token}", response_model=MemberInviteDetailsResponse)
def get_member_invite_details(token: str, db: DbSession = Depends(get_db)) -> dict:
    return member_service.get_member_invite_details(db, token)