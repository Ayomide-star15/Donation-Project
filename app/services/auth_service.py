from fastapi import HTTPException, status
from supabase import Client, create_client
from app.config import settings
from app.schemas.profile import DonorSignupRequest, PhoneSubmit
from app.schemas.auth import SetPasswordRequest, ResendInviteRequest


def signup_donor(admin: Client, payload: DonorSignupRequest) -> dict:
    admin.auth.admin.invite_user_by_email(
        payload.email,
        {
            "data": {
                "first_name": payload.first_name,
                "last_name": payload.last_name,
                "phone": payload.phone,
            },
            "redirect_to": settings.INVITE_REDIRECT_URL,
        },
    )
    return {"status": "invited"}


def resend_invite(admin: Client, payload: ResendInviteRequest) -> dict:
    admin.auth.admin.invite_user_by_email(
        payload.email,
        {"redirect_to": settings.INVITE_REDIRECT_URL},
    )
    return {"status": "invite resent"}


def set_password(payload: SetPasswordRequest) -> dict:
    client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
    client.postgrest.auth(payload.access_token)
    try:
        client.auth.update_user({"password": payload.new_password})
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired link")
    return {"status": "password set"}


def claim_pending_roles(db: Client, user_id: str, payload: PhoneSubmit) -> dict:
    db.table("profiles").update({"phone": payload.phone}).eq("id", user_id).execute()
    db.rpc("claim_pending_roles_by_phone").execute()
    return {"status": "ok"}