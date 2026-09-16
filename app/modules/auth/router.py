import uuid

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.config import settings
from app.core.database import get_db
from app.modules.auth.dependencies import AuthContext, get_auth_context
from app.modules.auth.models import Session
from app.modules.auth.schemas import (
    ChangePasswordRequest,
    LoginChallengeResponse,
    LoginRequest,
    MfaSetupRequest,
    MfaSetupResponse,
    MfaRecoveryRequest,
    MfaVerifyRequest,
    SessionResponse,
    TokenResponse,
    UserResponse,
)
from app.modules.auth.service import (
    authenticate_password,
    begin_mfa_setup,
    change_password,
    revoke_all_sessions,
    revoke_session,
    rotate_refresh_token,
    use_recovery_code_and_create_session,
    verify_mfa_and_create_session,
)


router = APIRouter(prefix="/auth", tags=["authentication"])


def _request_metadata(request: Request) -> tuple[str | None, str | None]:
    ip_address = request.client.host if request.client else None
    return ip_address, request.headers.get("user-agent")


def _validate_browser_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != settings.FRONTEND_URL.rstrip("/"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Origin is not allowed")


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=token,
        max_age=settings.REFRESH_TOKEN_DAYS * 24 * 60 * 60,
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite="lax",
        domain=settings.COOKIE_DOMAIN,
        path=f"{settings.API_V1_PREFIX}/auth",
    )


def _delete_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        domain=settings.COOKIE_DOMAIN,
        path=f"{settings.API_V1_PREFIX}/auth",
    )


@router.post("/login", response_model=LoginChallengeResponse)
def login(
    payload: LoginRequest,
    request: Request,
    db: DbSession = Depends(get_db),
) -> LoginChallengeResponse:
    ip_address, user_agent = _request_metadata(request)
    _, purpose, challenge = authenticate_password(
        db,
        str(payload.email),
        payload.password,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    next_step = "mfa_verify" if purpose == "mfa_verify" else "mfa_setup"
    return LoginChallengeResponse(next_step=next_step, challenge_token=challenge)


@router.post("/mfa/setup", response_model=MfaSetupResponse)
def setup_mfa(
    payload: MfaSetupRequest,
    db: DbSession = Depends(get_db),
) -> MfaSetupResponse:
    return MfaSetupResponse(provisioning_uri=begin_mfa_setup(db, payload.challenge_token))


@router.post("/mfa/verify", response_model=TokenResponse)
def verify_mfa(
    payload: MfaVerifyRequest,
    request: Request,
    response: Response,
    db: DbSession = Depends(get_db),
) -> TokenResponse:
    ip_address, user_agent = _request_metadata(request)
    issued = verify_mfa_and_create_session(
        db,
        payload.challenge_token,
        payload.code,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    _set_refresh_cookie(response, issued.refresh_token)
    return TokenResponse(
        access_token=issued.access_token,
        expires_in=settings.ACCESS_TOKEN_MINUTES * 60,
        recovery_codes=issued.recovery_codes,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    request: Request,
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=settings.REFRESH_COOKIE_NAME),
    db: DbSession = Depends(get_db),
) -> TokenResponse:
    _validate_browser_origin(request)
    if refresh_token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token is missing")
    issued = rotate_refresh_token(db, refresh_token)
    _set_refresh_cookie(response, issued.refresh_token)
    return TokenResponse(
        access_token=issued.access_token,
        expires_in=settings.ACCESS_TOKEN_MINUTES * 60,
    )


@router.post("/mfa/recover", response_model=TokenResponse)
def recover_mfa(
    payload: MfaRecoveryRequest,
    request: Request,
    response: Response,
    db: DbSession = Depends(get_db),
) -> TokenResponse:
    ip_address, user_agent = _request_metadata(request)
    issued = use_recovery_code_and_create_session(
        db,
        payload.challenge_token,
        payload.recovery_code,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    _set_refresh_cookie(response, issued.refresh_token)
    return TokenResponse(
        access_token=issued.access_token,
        expires_in=settings.ACCESS_TOKEN_MINUTES * 60,
    )


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    context: AuthContext = Depends(get_auth_context),
    db: DbSession = Depends(get_db),
) -> None:
    revoke_session(db, context.session, "logout")
    _delete_refresh_cookie(response)


@router.post("/logout-all", status_code=204)
def logout_all(
    response: Response,
    context: AuthContext = Depends(get_auth_context),
    db: DbSession = Depends(get_db),
) -> None:
    revoke_all_sessions(db, context.user.id, "logout_all")
    _delete_refresh_cookie(response)


@router.post("/change-password", status_code=204)
def update_password(
    payload: ChangePasswordRequest,
    response: Response,
    context: AuthContext = Depends(get_auth_context),
    db: DbSession = Depends(get_db),
) -> None:
    change_password(db, context.user, payload.current_password, payload.new_password)
    _delete_refresh_cookie(response)


@router.get("/me", response_model=UserResponse)
def me(context: AuthContext = Depends(get_auth_context)) -> UserResponse:
    return UserResponse.model_validate(context.user)


@router.get("/sessions", response_model=list[SessionResponse])
def list_sessions(
    context: AuthContext = Depends(get_auth_context),
    db: DbSession = Depends(get_db),
) -> list[Session]:
    return list(
        db.scalars(
            select(Session)
            .where(Session.user_id == context.user.id, Session.revoked_at.is_(None))
            .order_by(Session.last_used_at.desc())
        )
    )


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(
    session_id: uuid.UUID,
    context: AuthContext = Depends(get_auth_context),
    db: DbSession = Depends(get_db),
) -> None:
    session = db.get(Session, session_id)
    if session is None or session.user_id != context.user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    revoke_session(db, session, "user_revoked")
