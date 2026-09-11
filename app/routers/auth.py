from fastapi import APIRouter, Depends
from supabase import Client
from app.core.security import get_supabase, get_supabase_admin
from app.schemas.profile import DonorSignupRequest, PhoneSubmit 
router = APIRouter()

@router.post("/signup")
def signup_donor(payload: DonorSignupRequest, admin: Client = Depends(get_supabase_admin)):
    """Donor self-registration: creates the auth user and emails them a
    'set your password' link. The profiles row is created automatically
    by the DB trigger."""
    admin.auth.admin.invite_user_by_email(
        payload.email,
        {
            "data": {
                "first_name": payload.first_name,
                "last_name": payload.last_name,
                "phone": payload.phone,
            },
            "redirect_to": "https://your-frontend.com/set-password",
        },
    )
    return {"status": "invited"}

@router.post("/claim-pending-roles")
def claim_pending_roles(db: Client = Depends(get_supabase)):
    """Call right after a Google-signup user submits their phone number."""
    db.rpc("claim_pending_roles_by_phone").execute()
    return {"status": "ok"}