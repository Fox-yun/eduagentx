"""Student profile service — learning dimension tracking via LLM profiler agent."""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import UserProfile
from app.prompts.agents import PROFILER_SYSTEM, profiler_user
from app.services.llm import LLMError, llm_json

logger = structlog.get_logger()

# Default dimensions for new profiles
DEFAULT_DIMENSIONS = {
    "knowledge_depth": 50,
    "practice_ability": 50,
    "learning_efficiency": 50,
    "concept_grasp": 50,
    "problem_solving": 50,
}


class ProfileService:
    """Update student learning profile dimensions after assessments."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def update_after_assessment(
        self,
        user_id: str,
        node_title: str,
        score: float,
        passed: bool,
        weak_concepts: list[str],
    ) -> dict[str, Any] | None:
        """Update profile dimensions based on assessment result."""
        # Get or create profile
        result = await self.db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
        profile = result.scalar_one_or_none()
        if not profile:
            return None

        # Parse current dimensions
        current = profile.learning_dimensions if profile.learning_dimensions else dict(DEFAULT_DIMENSIONS)

        # Call LLM profiler
        try:
            llm_result = await llm_json(
                PROFILER_SYSTEM,
                profiler_user(node_title, score, passed, weak_concepts, current),
                temperature=0.3,
                max_tokens=512,
            )
            new_dims = llm_result.get("dimensions", {})
            # Validate and clamp dimensions
            for key in DEFAULT_DIMENSIONS:
                if key in new_dims:
                    new_dims[key] = max(0, min(100, int(new_dims[key])))
                elif key in current:
                    new_dims[key] = current[key]
                else:
                    new_dims[key] = DEFAULT_DIMENSIONS[key]

            profile.learning_dimensions = new_dims
            await self.db.flush()

            logger.info(
                "profile_updated",
                user_id=user_id,
                dimensions=new_dims,
                analysis=llm_result.get("analysis", ""),
            )
            return {
                "dimensions": new_dims,
                "analysis": llm_result.get("analysis", ""),
                "suggestion": llm_result.get("suggestion", ""),
            }
        except (LLMError, Exception) as e:
            logger.warning("profile_update_failed", error=str(e))
            # Fallback: simple rule-based update
            if passed and score >= 80:
                for key in current:
                    current[key] = min(100, current[key] + 3)
            elif not passed:
                for key in current:
                    current[key] = max(0, current[key] - 2)
            profile.learning_dimensions = current
            await self.db.flush()
            return None
