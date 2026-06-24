"""User profile and onboarding API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_deps import require_active_user
from app.core.database import get_db
from app.core.errors import ApiError
from app.core.security import hash_password, verify_password
from app.models.user import AuthSession, User
from app.services.user import UserService

router = APIRouter()


class UpdateProfileRequest(BaseModel):
    display_name: str | None = None
    preferred_language: str | None = None
    timezone: str | None = None


class OnboardingRequest(BaseModel):
    role: str
    learning_interests: list[str]
    learning_preferences: list[str]
    preferred_language: str = "zh"
    weekly_hours: int = 10
    use_diagnostic: bool = True
    use_knowledge_base: bool = False


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.get("/me")
async def get_me(
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get current user with profile."""
    service = UserService(db)
    return await service.get_profile(user.id)


@router.patch("/me")
async def update_me(
    body: UpdateProfileRequest,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Update current user profile."""
    service = UserService(db)
    return await service.update_profile(
        user_id=user.id,
        display_name=body.display_name,
        preferred_language=body.preferred_language,
        timezone=body.timezone,
    )


@router.post("/me/onboarding")
async def complete_onboarding(
    body: OnboardingRequest,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Complete user onboarding."""
    service = UserService(db)
    return await service.complete_onboarding(
        user_id=user.id,
        role=body.role,
        learning_interests=body.learning_interests,
        learning_preferences=body.learning_preferences,
        preferred_language=body.preferred_language,
        weekly_hours=body.weekly_hours,
        use_diagnostic=body.use_diagnostic,
        use_knowledge_base=body.use_knowledge_base,
    )


@router.put("/me/profile")
async def update_profile(
    body: UpdateProfileRequest,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Update user profile (PUT endpoint)."""
    service = UserService(db)
    return await service.update_profile(
        user_id=user.id,
        display_name=body.display_name,
        preferred_language=body.preferred_language,
        timezone=body.timezone,
    )


@router.put("/me/password")
async def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Change user password."""
    if not verify_password(body.current_password, user.password_hash):
        raise ApiError(code="INVALID_PASSWORD", message="Current password is incorrect", status_code=400)

    from app.core.security import validate_password_strength

    validate_password_strength(body.new_password)

    user.password_hash = hash_password(body.new_password)
    await db.flush()

    return {"message": "Password changed successfully"}


@router.get("/me/sessions")
async def list_sessions(
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List user's active sessions."""
    result = await db.execute(
        select(AuthSession).where(
            AuthSession.user_id == user.id,
            AuthSession.revoked_at.is_(None),
        )
    )
    sessions = list(result.scalars().all())

    return {
        "items": [
            {
                "session_id": s.id,
                "user_agent": s.user_agent,
                "ip_address": s.ip_address,
                "created_at": str(s.created_at),
                "last_used_at": str(s.last_used_at),
            }
            for s in sessions
        ],
        "next_cursor": None,
        "total": len(sessions),
    }
