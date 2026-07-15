"""Learning goal service."""

from __future__ import annotations

import json
import uuid

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.pagination import decode_cursor, encode_cursor
from app.models.goal import LearningGoal, validate_goal_transition

logger = structlog.get_logger()


class GoalService:
    """Learning goal business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_goal(
        self,
        user_id: str,
        raw_goal: str,
        current_level: str | None = None,
        target_level: str | None = None,
        duration_weeks: int | None = None,
        weekly_hours: int | None = None,
        preferences: list[str] | None = None,
        use_diagnostic: bool = True,
        use_knowledge_base: bool = False,
        content_language: str = "zh",
    ) -> dict:
        """Create a new learning goal."""
        goal = LearningGoal(
            id=str(uuid.uuid4()),
            user_id=user_id,
            title=raw_goal[:500],
            raw_description=raw_goal,
            current_level=current_level,
            target_level=target_level,
            weekly_hours=weekly_hours,
            preferences=json.dumps(preferences or []),
            use_diagnostic=use_diagnostic,
            use_knowledge_base=use_knowledge_base,
            content_language=content_language,
            status="draft",
        )
        self.db.add(goal)
        await self.db.flush()
        await self.db.commit()

        return {
            "goal": goal,
            "next_step": "clarify" if use_diagnostic else "generating",
        }

    async def get_goal(self, goal_id: str, user_id: str) -> LearningGoal:
        """Get a goal by ID, ensuring ownership."""
        result = await self.db.execute(
            select(LearningGoal).where(
                LearningGoal.id == goal_id,
                LearningGoal.user_id == user_id,
            )
        )
        goal = result.scalar_one_or_none()
        if not goal:
            raise ApiError(code="GOAL_NOT_FOUND", message="Goal not found", status_code=404)
        return goal

    async def list_goals(
        self,
        user_id: str,
        cursor: str | None = None,
        limit: int = 20,
    ) -> dict:
        """List goals for a user with cursor pagination."""
        if limit < 1 or limit > 100:
            limit = 20

        query = select(LearningGoal).where(
            LearningGoal.user_id == user_id,
            LearningGoal.status != "archived",
        )

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply cursor
        if cursor:
            cursor_data = decode_cursor(cursor)
            cursor_created = cursor_data.get("order")
            cursor_id = cursor_data.get("id")
            if cursor_created and cursor_id:
                query = query.where(
                    (LearningGoal.created_at < cursor_created)
                    | ((LearningGoal.created_at == cursor_created) & (LearningGoal.id < cursor_id))
                )

        query = query.order_by(LearningGoal.created_at.desc(), LearningGoal.id.desc())
        query = query.limit(limit + 1)

        result = await self.db.execute(query)
        goals = list(result.scalars().all())

        has_next = len(goals) > limit
        if has_next:
            goals = goals[:limit]
            last = goals[-1]
            next_cursor = encode_cursor(
                {
                    "order": str(last.created_at),
                    "id": last.id,
                }
            )
        else:
            next_cursor = None

        return {
            "items": goals,
            "next_cursor": next_cursor,
            "total": total,
        }

    async def update_goal(
        self,
        goal_id: str,
        user_id: str,
        **kwargs: object,
    ) -> LearningGoal:
        """Update a goal."""
        goal = await self.get_goal(goal_id, user_id)

        for key, value in kwargs.items():
            if value is not None and hasattr(goal, key):
                setattr(goal, key, value)

        await self.db.flush()
        await self.db.commit()
        return goal

    async def transition_goal(
        self,
        goal_id: str,
        user_id: str,
        target_status: str,
        task_id: str | None = None,
        *,
        commit: bool = True,
    ) -> LearningGoal:
        """Transition a goal to a new status."""
        goal = await self.get_goal(goal_id, user_id)

        if not validate_goal_transition(goal.status, target_status):
            raise ApiError(
                code="INVALID_TRANSITION",
                message=f"Cannot transition from '{goal.status}' to '{target_status}'",
                status_code=400,
            )

        goal.status = target_status
        if task_id:
            goal.active_task_id = task_id
        elif target_status in ("ready", "active", "completed"):
            # Clear stale task reference when goal reaches a stable state
            goal.active_task_id = None

        await self.db.flush()
        if commit:
            await self.db.commit()
        return goal

    async def delete_goal(self, goal_id: str, user_id: str) -> None:
        """Archive a goal (soft delete)."""
        goal = await self.get_goal(goal_id, user_id)
        goal.status = "archived"
        await self.db.flush()
        await self.db.commit()
