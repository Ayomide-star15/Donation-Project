from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session as DbSession

from app.core.database import get_db
from app.modules.communities import service
from app.modules.communities.schemas import (
    AcceptInviteRequest,
    AcceptInviteResponse,
    InviteDetailsResponse,
)


router = APIRouter(prefix="/invites", tags=["invites"])


@router.get("/{token}", response_model=InviteDetailsResponse)
def get_invite_details(token: str, db: DbSession = Depends(get_db)) -> dict:
    return service.get_invite_details(db, token)


@router.post(
    "/{token}/accept",
    response_model=AcceptInviteResponse,
    status_code=status.HTTP_201_CREATED,
)
def accept_invite(
    token: str,
    payload: AcceptInviteRequest,
    db: DbSession = Depends(get_db),
) -> dict:
    return service.accept_invite(db, token, payload)


@router.post("/{token}/decline", status_code=status.HTTP_204_NO_CONTENT)
def decline_invite(token: str, db: DbSession = Depends(get_db)) -> None:
    service.decline_invite(db, token)