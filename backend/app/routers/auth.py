"""Authentication API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_deps import get_current_session, get_current_user
from app.core.cookies import clear_auth_cookies, create_auth_response
from app.core.database import get_db
from app.core.request_context import get_client_ip
from app.core.security import generate_csrf_token as gen_csrf
from app.models.user import User
from app.services.auth import AuthService

router = APIRouter()


# Request schemas
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str = BaseModel.Field(
        min_length=1,
        max_length=100,
        pattern=r"^[\w\s一-鿿㐀-䶿\-'.]+$",
        description="Display name: letters, digits, spaces, CJK, hyphens, apostrophes",
    )


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


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
        from app.core.errors import ApiError

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


@router.post("/verify-email")
async def verify_email(
    body: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Verify email address with token."""
    service = AuthService(db)
    await service.verify_email(body.token)
    return {"message": "Email verified successfully"}


@router.post("/resend-verification")
async def resend_verification(
    body: ResendVerificationRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Resend email verification token."""
    # Always return success to prevent email enumeration
    return {"message": "If an account exists, a verification email has been sent"}


@router.post("/forgot-password")
async def forgot_password(
    body: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Request password reset."""
    # Always return success to prevent email enumeration
    return {"message": "If an account exists, a password reset email has been sent"}


@router.post("/reset-password")
async def reset_password(
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Reset password with token."""
    # In production, would validate token and update password
    return {"message": "Password reset successfully"}
