from fastapi import APIRouter, Depends
from supabase import Client
from app.core.security import get_supabase, get_supabase_admin, get_current_user
from app.schemas.profile import DonorSignupRequest, PhoneSubmit
from app.schemas.auth import SetPasswordRequest, ResendInviteRequest
from app.services import auth_service

router = APIRouter()

@router.post("/signup")
def signup_donor(payload: DonorSignupRequest, admin: Client = Depends(get_supabase_admin)):
    return auth_service.signup_donor(admin, payload)

@router.post("/resend-invite")
def resend_invite(payload: ResendInviteRequest, admin: Client = Depends(get_supabase_admin)):
    return auth_service.resend_invite(admin, payload)

@router.post("/set-password")
def set_password(payload: SetPasswordRequest):
    return auth_service.set_password(payload)

@router.post("/claim-pending-roles")
def claim_pending_roles(
    payload: PhoneSubmit,
    db: Client = Depends(get_supabase),
    user: dict = Depends(get_current_user),
):
    return auth_service.claim_pending_roles(db, user["sub"], payload)