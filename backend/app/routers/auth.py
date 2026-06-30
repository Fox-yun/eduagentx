"""Authentication API endpoints."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_deps import get_current_session, get_current_user
from app.core.cookies import clear_auth_cookies, create_auth_response
from app.core.database import get_db
from app.core.errors import ApiError
from app.core.request_context import get_client_ip
from app.core.security import generate_csrf_token as gen_csrf
from app.core.security import hash_password
from app.models.user import User
from app.services.auth import AuthService

router = APIRouter()


# Request schemas
class RegisterRequest(BaseModel):
    """Registration request with terms acceptance."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str
    display_name: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[\w\s一-鿿㐀-䶿\-'.]+$",
        description="Display name: letters, digits, spaces, CJK, hyphens, apostrophes",
    )
    accept_terms: Literal[True] = Field(description="User must accept terms of service")


class LoginRequest(BaseModel):
    """Login request with optional remember_me."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str
    remember_me: bool = False


class VerifyEmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str


class ResendVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ForgotPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str
    password: str = Field(min_length=8, max_length=128)


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


# Response schemas
class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    email: str
    display_name: str
    email_verified: bool
    onboarding_completed: bool
    status: str


class RegisterResponse(BaseModel):
    next_step: str
    user: UserResponse


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: str
    user_agent: str | None
    ip_address: str | None
    created_at: str
    last_used_at: str | None
    is_current: bool


@router.get("/csrf")
async def get_csrf_token(request: Request) -> JSONResponse:
    """Get a CSRF token. Sets the csrftoken cookie."""
    from app.config import get_settings

    settings = get_settings()
    csrf_token = gen_csrf()
    response = JSONResponse(content={"csrf_token": csrf_token})
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        max_age=3600,
        path="/",
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain,
    )
    return response


@router.post("/register", response_model=RegisterResponse)
async def register(
    body: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    """Register a new user account."""
    service = AuthService(db)
    result = await service.register(
        email=body.email,
        password=body.password,
        display_name=body.display_name,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    user = result["user"]
    return RegisterResponse(
        next_step=result["next_step"],
        user=UserResponse(
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            email_verified=user.email_verified_at is not None,
            onboarding_completed=user.onboarding_completed_at is not None,
            status=user.status,
        ),
    )


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Authenticate and create a session."""
    service = AuthService(db)
    result = await service.login(
        email=body.email,
        password=body.password,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        remember_me=body.remember_me,
    )

    user = result["user"]
    return create_auth_response(
        access_token=result["access_token"],
        refresh_token=result["refresh_token"],
        csrf_token=result["csrf_token"],
        body={
            "user_id": user.id,
            "display_name": user.display_name,
            "email": user.email,
            "email_verified": user.email_verified_at is not None,
            "onboarding_completed": user.onboarding_completed_at is not None,
            "status": user.status,
        },
    )


@router.get("/me", response_model=UserResponse)
async def get_me(
    user: User = Depends(get_current_user),
) -> UserResponse:
    """Get the current authenticated user."""
    return UserResponse(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        email_verified=user.email_verified_at is not None,
        onboarding_completed=user.onboarding_completed_at is not None,
        status=user.status,
    )


@router.post("/refresh")
async def refresh(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Refresh the access token."""
    # Read refresh token from cookie
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise ApiError(code="MISSING_TOKEN", message="Refresh token not found", status_code=401)

    service = AuthService(db)
    result = await service.refresh(
        refresh_token=refresh_token,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    return create_auth_response(
        access_token=result["access_token"],
        refresh_token=result["refresh_token"],
        csrf_token=result["csrf_token"],
    )


@router.post("/logout")
async def logout(
    request: Request,
    session: dict[str, str] = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Logout the current session."""
    service = AuthService(db)
    await service.logout(
        session_id=session["session_id"],
        user_id=session["user_id"],
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    response = JSONResponse(content={"message": "Logged out"})
    clear_auth_cookies(response)
    return response


@router.post("/logout-all")
async def logout_all(
    request: Request,
    session: dict[str, str] = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Logout from all sessions."""
    service = AuthService(db)
    await service.logout_all(
        user_id=session["user_id"],
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    response = JSONResponse(content={"message": "All sessions logged out"})
    clear_auth_cookies(response)
    return response


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    user: User = Depends(get_current_user),
    session: dict[str, str] = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Change the current user's password."""
    from app.core.security import verify_password

    if not verify_password(body.current_password, user.password_hash):
        raise ApiError(code="INVALID_PASSWORD", message="Current password is incorrect", status_code=400)

    from app.core.security import validate_password_strength

    validate_password_strength(body.new_password)

    # Update password
    user.password_hash = hash_password(body.new_password)
    await db.flush()

    # Revoke all other sessions for security
    service = AuthService(db)
    await service.logout_all(
        user_id=user.id,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    response = JSONResponse(content={"message": "Password changed successfully"})
    clear_auth_cookies(response)
    return response


@router.get("/sessions")
async def list_sessions(
    user: User = Depends(get_current_user),
    session: dict[str, str] = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List all active sessions for the current user."""
    from sqlalchemy import select

    from app.common.datetime import to_iso_string
    from app.models.user import AuthSession

    result = await db.execute(
        select(AuthSession)
        .where(
            AuthSession.user_id == user.id,
            AuthSession.revoked_at.is_(None),
        )
        .order_by(AuthSession.created_at.desc())
    )
    sessions = list(result.scalars().all())

    return {
        "sessions": [
            {
                "session_id": s.id,
                "user_agent": s.user_agent,
                "ip_address": s.ip_address,
                "created_at": to_iso_string(s.created_at),
                "last_used_at": to_iso_string(s.last_used_at) if s.last_used_at else None,
                "is_current": s.id == session["session_id"],
            }
            for s in sessions
        ]
    }


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    request: Request,
    session: dict[str, str] = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete (revoke) a specific session."""
    service = AuthService(db)
    await service.logout(
        session_id=session_id,
        user_id=session["user_id"],
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return {"message": "Session revoked"}


@router.post("/verify-email")
async def verify_email(
    body: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Verify email address with token."""
    service = AuthService(db)
    user = await service.verify_email(body.token)
    return JSONResponse(
        content={
            "message": "Email verified successfully",
            "user": {
                "user_id": user.id,
                "email": user.email,
                "display_name": user.display_name,
                "email_verified": True,
                "onboarding_completed": user.onboarding_completed_at is not None,
                "status": user.status,
            },
        }
    )


@router.post("/resend-verification")
async def resend_verification(
    request: Request,
    session: dict[str, str] = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Resend email verification token."""
    service = AuthService(db)
    return await service.resend_verification(
        user_id=session["user_id"],
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


@router.post("/forgot-password")
async def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Request password reset. Does not leak email existence."""
    service = AuthService(db)
    return await service.request_password_reset(
        email=body.email,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


@router.post("/reset-password")
async def reset_password(
    body: ResetPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Reset password with token."""
    service = AuthService(db)
    await service.reset_password(
        token=body.token,
        new_password=body.password,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    response = JSONResponse(content={"message": "Password reset successfully"})
    clear_auth_cookies(response)
    return response
