from fastapi import APIRouter, Depends
from supabase import Client
from app.core.security import get_supabase

router = APIRouter()

@router.post("/claim-pending-roles")
def claim_pending_roles(db: Client = Depends(get_supabase)):
    """Call right after a Google-signup user submits their phone number."""
    db.rpc("claim_pending_roles_by_phone").execute()
    return {"status": "ok"}