"""Authentication dependencies for FastAPI routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.datetime import utc_now
from app.common.enums import UserStatus
from app.core.database import get_db
from app.core.errors import ApiError
from app.core.security import decode_access_token
from app.models.user import AuthSession, User


async def get_current_session(
    request: Request,
    access_token: Annotated[str | None, Cookie()] = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Extract and validate the current session from the access token cookie.

    Validates:
    - Access token exists and is valid JWT
    - Session exists in database and is not revoked
    - Session has not expired
    - User exists and is not deleted/locked/disabled
    """
    if not access_token:
        raise ApiError(code="UNAUTHENTICATED", message="Not authenticated", status_code=401)

    try:
        payload = decode_access_token(access_token)
    except ApiError:
        raise

    user_id = payload.get("sub")
    session_id = payload.get("sid")

    if not user_id or not session_id:
        raise ApiError(code="INVALID_TOKEN", message="Invalid token payload", status_code=401)

    # Validate session exists and is not revoked
    result = await db.execute(
        select(AuthSession).where(
            AuthSession.id == session_id,
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
        )
    )
    session = result.scalar_one_or_none()

    if not session:
        raise ApiError(code="SESSION_REVOKED", message="Session has been revoked", status_code=401)

    # Check session expiration
    if session.expires_at < utc_now():
        raise ApiError(code="SESSION_EXPIRED", message="Session has expired", status_code=401)

    return {"user_id": str(user_id), "session_id": str(session_id)}


async def get_current_user(
    session: dict[str, str] = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Get the current authenticated user."""
    user_id = session["user_id"]

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise ApiError(code="USER_NOT_FOUND", message="User not found", status_code=404)

    if user.status == UserStatus.DELETED.value:
        raise ApiError(code="USER_NOT_FOUND", message="User not found", status_code=404)

    return user


async def require_verified_user(
    user: User = Depends(get_current_user),
) -> User:
    """Require that the current user has verified their email."""
    if not user.email_verified_at:
        raise ApiError(code="EMAIL_NOT_VERIFIED", message="Email verification required", status_code=403)
    return user


async def require_active_user(
    user: User = Depends(require_verified_user),
) -> User:
    """Require that the current user account is active.

    Depends on require_verified_user to ensure email is verified first.
    """
    if user.status == UserStatus.LOCKED.value:
        raise ApiError(code="ACCOUNT_LOCKED", message="Account is locked", status_code=403)
    if user.status == UserStatus.DISABLED.value:
        raise ApiError(code="ACCOUNT_DISABLED", message="Account is disabled", status_code=403)
    return user


async def require_learning_user(
    user: User = Depends(require_active_user),
) -> User:
    """Require that the current user has completed onboarding.

    Depends on require_active_user to ensure account is active.
    Used for Goal/Task/Path/Unit/Knowledge endpoints.
    """
    if not user.onboarding_completed_at:
        raise ApiError(code="ONBOARDING_REQUIRED", message="Onboarding is required", status_code=403)
    return user
