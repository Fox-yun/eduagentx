"""User service for profile and onboarding management."""

from __future__ import annotations

import json
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.datetime import utc_now
from app.core.errors import ApiError
from app.models.user import User, UserProfile

logger = structlog.get_logger()


class UserService:
    """User profile and onboarding business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_profile(self, user_id: str) -> dict[str, Any]:
        """Get user profile."""
        profile_result = await self.db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
        profile = profile_result.scalar_one_or_none()
        if not profile:
            raise ApiError(code="PROFILE_NOT_FOUND", message="User profile not found", status_code=404)

        user_result = await self.db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            raise ApiError(code="USER_NOT_FOUND", message="User not found", status_code=404)

        return {
            "user_id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "email_verified": user.email_verified_at is not None,
            "onboarding_completed": user.onboarding_completed_at is not None,
            "status": user.status,
            "profile": {
                "role": profile.role,
                "preferred_language": profile.preferred_language,
                "timezone": profile.timezone,
                "weekly_hours": profile.weekly_hours,
                "learning_interests": json.loads(profile.learning_interests) if profile.learning_interests else [],
                "learning_preferences": json.loads(profile.learning_preferences)
                if profile.learning_preferences
                else [],
                "use_diagnostic": profile.use_diagnostic,
                "use_knowledge_base": profile.use_knowledge_base,
            },
        }

    async def update_profile(
        self,
        user_id: str,
        display_name: str | None = None,
        preferred_language: str | None = None,
        timezone: str | None = None,
    ) -> dict[str, Any]:
        """Update user profile."""
        profile_result = await self.db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
        profile = profile_result.scalar_one_or_none()
        if not profile:
            raise ApiError(code="PROFILE_NOT_FOUND", message="User profile not found", status_code=404)

        user_result = await self.db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            raise ApiError(code="USER_NOT_FOUND", message="User not found", status_code=404)

        if display_name is not None:
            user.display_name = display_name.strip()
        if preferred_language is not None:
            profile.preferred_language = preferred_language
        if timezone is not None:
            profile.timezone = timezone

        await self.db.flush()
        return await self.get_profile(user_id)

    async def complete_onboarding(
        self,
        user_id: str,
        role: str,
        learning_interests: list[str],
        learning_preferences: list[str],
        preferred_language: str = "zh",
        weekly_hours: int = 10,
        use_diagnostic: bool = True,
        use_knowledge_base: bool = False,
    ) -> dict[str, Any]:
        """Complete user onboarding."""
        profile_result = await self.db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
        profile = profile_result.scalar_one_or_none()
        if not profile:
            raise ApiError(code="PROFILE_NOT_FOUND", message="User profile not found", status_code=404)

        user_result = await self.db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            raise ApiError(code="USER_NOT_FOUND", message="User not found", status_code=404)

        # Update profile
        profile.role = role
        profile.learning_interests = json.dumps(learning_interests)
        profile.learning_preferences = json.dumps(learning_preferences)
        profile.preferred_language = preferred_language
        profile.weekly_hours = weekly_hours
        profile.use_diagnostic = use_diagnostic
        profile.use_knowledge_base = use_knowledge_base

        # Mark onboarding as complete
        user.onboarding_completed_at = utc_now()

        await self.db.flush()
        return await self.get_profile(user_id)
