import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.config import settings
from app.core.database import get_db
from app.modules.auth.dependencies import AuthContext, get_auth_context
from app.modules.auth.models import Session
from app.modules.auth.schemas import (
    AuthenticatedResponse,
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    OtpChallengeResponse,
    OtpResendRequest,
    OtpVerifyRequest,
    SessionResponse,
    UserResponse,
)
from app.modules.auth.service import (
    authenticate_password,
    change_password,
    resend_email_otp,
    revoke_all_sessions,
    revoke_session,
    verify_email_otp,
)
from app.modules.notifications.email import EmailService, get_email_service

router = APIRouter(prefix="/auth", tags=["authentication"])


def _request_metadata(request: Request) -> tuple[str | None, str | None]:
    ip_address = request.client.host if request.client else None
    return ip_address, request.headers.get("user-agent")


def _validate_browser_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    allowed_origins = {
        settings.FRONTEND_URL.rstrip("/"),
        settings.API_PUBLIC_URL.rstrip("/"),
    }
    if origin and origin.rstrip("/") not in allowed_origins:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Origin is not allowed")


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.SESSION_HOURS * 60 * 60,
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite="lax",
        domain=settings.COOKIE_DOMAIN,
        path="/",
    )


def _delete_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        domain=settings.COOKIE_DOMAIN,
        path="/",
    )


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession = Depends(get_db),
    email_service: EmailService = Depends(get_email_service),
) -> LoginResponse:
    _validate_browser_origin(request)
    ip_address, user_agent = _request_metadata(request)
    result = authenticate_password(
        db,
        email_service,
        str(payload.email),
        payload.password,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    if result.issued_session:
        _set_session_cookie(response, result.issued_session.raw_token)
        return LoginResponse(status="authenticated")

    assert result.challenge is not None
    return LoginResponse(
        status="otp_required",
        challenge_id=result.challenge.id,
        expires_in=settings.OTP_EXPIRY_MINUTES * 60,
        masked_email=result.masked_email,
    )


@router.post("/otp/verify", response_model=AuthenticatedResponse)
def verify_otp(
    payload: OtpVerifyRequest,
    request: Request,
    response: Response,
    db: DbSession = Depends(get_db),
) -> AuthenticatedResponse:
    _validate_browser_origin(request)
    ip_address, user_agent = _request_metadata(request)
    issued = verify_email_otp(
        db,
        payload.challenge_id,
        payload.code,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    _set_session_cookie(response, issued.raw_token)
    return AuthenticatedResponse()


@router.post("/otp/resend", response_model=OtpChallengeResponse)
def resend_otp(
    payload: OtpResendRequest,
    request: Request,
    db: DbSession = Depends(get_db),
    email_service: EmailService = Depends(get_email_service),
) -> OtpChallengeResponse:
    _validate_browser_origin(request)
    ip_address, user_agent = _request_metadata(request)
    challenge, masked_email = resend_email_otp(
        db,
        email_service,
        payload.challenge_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return OtpChallengeResponse(
        challenge_id=challenge.id,
        expires_in=settings.OTP_EXPIRY_MINUTES * 60,
        resend_after=settings.OTP_RESEND_COOLDOWN_SECONDS,
        masked_email=masked_email,
    )


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    context: AuthContext = Depends(get_auth_context),
    db: DbSession = Depends(get_db),
) -> None:
    _validate_browser_origin(request)
    revoke_session(db, context.session, "logout")
    _delete_session_cookie(response)


@router.post("/logout-all", status_code=204)
def logout_all(
    request: Request,
    response: Response,
    context: AuthContext = Depends(get_auth_context),
    db: DbSession = Depends(get_db),
) -> None:
    _validate_browser_origin(request)
    revoke_all_sessions(db, context.user.id, "logout_all")
    _delete_session_cookie(response)


@router.post("/change-password", status_code=204)
def update_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    context: AuthContext = Depends(get_auth_context),
    db: DbSession = Depends(get_db),
) -> None:
    _validate_browser_origin(request)
    change_password(db, context.user, payload.current_password, payload.new_password)
    _delete_session_cookie(response)


@router.get("/session", response_model=UserResponse)
@router.get("/me", response_model=UserResponse, include_in_schema=False)
def current_session(context: AuthContext = Depends(get_auth_context)) -> UserResponse:
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
            .order_by(Session.last_seen_at.desc())
        )
    )


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(
    session_id: uuid.UUID,
    request: Request,
    response: Response,
    context: AuthContext = Depends(get_auth_context),
    db: DbSession = Depends(get_db),
) -> None:
    _validate_browser_origin(request)
    session = db.get(Session, session_id)
    if session is None or session.user_id != context.user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    revoke_session(db, session, "user_revoked")
    if session.id == context.session.id:
        _delete_session_cookie(response)
