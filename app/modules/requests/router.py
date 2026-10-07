from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session as DbSession

from app.core.database import get_db
from app.modules.auth.dependencies import AuthContext, get_auth_context
from app.modules.requests import service
from app.modules.requests.schemas import CreateRequestPayload, RequestResponse


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