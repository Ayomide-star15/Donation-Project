from datetime import datetime
from pydantic import BaseModel


class DashboardStats(BaseModel):
    # KPI cards from the screenshots
    total_donations: int
    donations_this_week: int
    active_requests: int
    pending_overrides: int
    cooldown_pool: int
    total_communities: int
    active_communities: int

    # Extra platform health metrics
    total_users: int
    active_users: int
    total_donors: int


class RecentRequestItem(BaseModel):
    id: str
    reference_code: str
    blood_type_needed: str
    status: str
    urgency: str
    community_name: str
    created_at: datetime


class SuperAdminDashboardResponse(BaseModel):
    generated_at: datetime
    stats: DashboardStats
    recent_requests: list[RecentRequestItem]