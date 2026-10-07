from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DbSession

from app.core.database import get_db
from app.modules.auth.dependencies import AuthContext, get_auth_context
from app.modules.communities import member_service
from app.modules.communities.member_schemas import MyProfileResponse


router = APIRouter(prefix="/me", tags=["community member"])


@router.get("/profile", response_model=MyProfileResponse)
def get_my_profile(
    context: AuthContext = Depends(get_auth_context),
    db: DbSession = Depends(get_db),
) -> dict:
    """Full member profile: account info + community membership."""
    return member_service.get_my_profile(db, context.user)