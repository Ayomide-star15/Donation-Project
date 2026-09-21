import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session as DbSession

from app.core.database import get_db
from app.modules.auth.dependencies import AuthContext, require_super_admin
from app.modules.invites import service
from app.modules.invites.schemas import InviteCreateRequest, InviteResponse
from app.modules.notifications.email import EmailService, get_email_service


router = APIRouter(prefix="/admin/invites", tags=["admin:invites"])


@router.post("", response_model=InviteResponse, status_code=status.HTTP_201_CREATED)
def create_invite(
    payload: InviteCreateRequest,
    context: AuthContext = Depends(require_super_admin),
    db: DbSession = Depends(get_db),
    email_service: EmailService = Depends(get_email_service),
):
    return service.create_invite(db, email_service, payload, context.user)


@router.get("", response_model=list[InviteResponse])
def list_invites(
    context: AuthContext = Depends(require_super_admin),
    db: DbSession = Depends(get_db),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
):
    return service.list_invites(db, limit=limit, offset=offset)


@router.delete("/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invite(
    invite_id: uuid.UUID,
    context: AuthContext = Depends(require_super_admin),
    db: DbSession = Depends(get_db),
):
    service.revoke_invite(db, invite_id, context.user)