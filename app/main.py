from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.modules.auth.router import router as auth_router
from app.modules.locations.router import router as locations_router
from app.modules.hospitals.router import (
    admin_router as hospitals_admin_router,
    public_router as hospitals_public_router
)
from app.modules.invites.router import router as invites_router

app = FastAPI(title=settings.APP_NAME)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)
app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
app.include_router(locations_router, prefix=settings.API_V1_PREFIX)
app.include_router(hospitals_admin_router, prefix=settings.API_V1_PREFIX)
app.include_router(hospitals_public_router, prefix=settings.API_V1_PREFIX)
app.include_router(invites_router, prefix=settings.API_V1_PREFIX)
@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}
