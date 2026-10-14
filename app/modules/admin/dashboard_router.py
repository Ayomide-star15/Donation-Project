from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session as DbSession

from app.core.database import get_db
from app.modules.admin import dashboard_service
from app.modules.admin.dashboard_schemas import SuperAdminDashboardResponse
from app.modules.auth.dependencies import AuthContext, require_super_admin


router = APIRouter(prefix="/admin", tags=["super admin: dashboard"])


@router.get("/dashboard", response_model=SuperAdminDashboardResponse)
def get_dashboard(
    context: AuthContext = Depends(require_super_admin),
    db: DbSession = Depends(get_db),
    recent_limit: int = Query(default=5, ge=1, le=20),
) -> dict:
    """Super Admin dashboard: platform-wide summary + recent activity."""
    return dashboard_service.get_dashboard(db, recent_limit=recent_limit)