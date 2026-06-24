"""Learning goal API endpoints."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas import CursorPage
from app.core.auth_deps import require_learning_user
from app.core.database import get_db
from app.models.user import User
from app.services.goal import GoalService

router = APIRouter()


class CreateGoalRequest(BaseModel):
    raw_goal: str
    current_level: str | None = None
    target_level: str | None = None
    duration_weeks: int | None = None
    weekly_hours: int | None = None
    preferences: list[str] | None = None
    use_diagnostic: bool = True
    use_knowledge_base: bool = False
    content_language: str = "zh"


class UpdateGoalRequest(BaseModel):
    title: str | None = None
    normalized_goal: str | None = None
    current_level: str | None = None
    target_level: str | None = None
    weekly_hours: int | None = None


class GoalResponse(BaseModel):
    goal_id: str
    raw_goal: str
    normalized_goal: str | None
    current_level: str | None
    target_level: str | None
    duration_weeks: int | None
    weekly_hours: int | None
    preferences: list[str]
    use_diagnostic: bool
    use_knowledge_base: bool
    status: str
    next_step: str | None
    active_task_id: str | None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


def _goal_to_response(goal: Any) -> GoalResponse:
    """Convert a LearningGoal model to a response."""
    from app.common.datetime import to_iso_string

    return GoalResponse(
        goal_id=goal.id,
        raw_goal=goal.raw_description,
        normalized_goal=goal.normalized_goal,
        current_level=goal.current_level,
        target_level=goal.target_level,
        duration_weeks=None,
        weekly_hours=goal.weekly_hours,
        preferences=json.loads(goal.preferences) if goal.preferences else [],
        use_diagnostic=goal.use_diagnostic,
        use_knowledge_base=goal.use_knowledge_base,
        status=goal.status,
        next_step=_get_next_step(goal.status),
        active_task_id=goal.active_task_id,
        created_at=to_iso_string(goal.created_at) or "",
        updated_at=to_iso_string(goal.updated_at) or "",
    )


def _get_next_step(status: str) -> str | None:
    """Determine the next step based on goal status."""
    mapping = {
        "draft": "clarify",
        "clarifying": "clarify",
        "diagnosing": "diagnostic",
        "planning": "generating",
        "ready": "review",
        "active": "active",
    }
    return mapping.get(status)


@router.post("", response_model=dict)
async def create_goal(
    body: CreateGoalRequest,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a new learning goal."""
    service = GoalService(db)
    result = await service.create_goal(
        user_id=user.id,
        raw_goal=body.raw_goal,
        current_level=body.current_level,
        target_level=body.target_level,
        duration_weeks=body.duration_weeks,
        weekly_hours=body.weekly_hours,
        preferences=body.preferences,
        use_diagnostic=body.use_diagnostic,
        use_knowledge_base=body.use_knowledge_base,
        content_language=body.content_language,
    )

    goal = result["goal"]
    return {
        "goal_id": goal.id,
        "next_step": result["next_step"],
        "active_task_id": goal.active_task_id,
    }


@router.get("", response_model=CursorPage[GoalResponse])
async def list_goals(
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> CursorPage[GoalResponse]:
    """List learning goals with cursor pagination."""
    service = GoalService(db)
    result = await service.list_goals(
        user_id=user.id,
        cursor=cursor,
        limit=limit,
    )

    return CursorPage(
        items=[_goal_to_response(g) for g in result["items"]],
        next_cursor=result["next_cursor"],
        total=result["total"],
    )


@router.get("/{goal_id}", response_model=GoalResponse)
async def get_goal(
    goal_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> GoalResponse:
    """Get a specific learning goal."""
    service = GoalService(db)
    goal = await service.get_goal(goal_id, user.id)
    return _goal_to_response(goal)


@router.patch("/{goal_id}", response_model=GoalResponse)
async def update_goal(
    goal_id: str,
    body: UpdateGoalRequest,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> GoalResponse:
    """Update a learning goal."""
    service = GoalService(db)
    goal = await service.update_goal(
        goal_id=goal_id,
        user_id=user.id,
        title=body.title,
        normalized_goal=body.normalized_goal,
        current_level=body.current_level,
        target_level=body.target_level,
        weekly_hours=body.weekly_hours,
    )
    return _goal_to_response(goal)


@router.delete("/{goal_id}")
async def delete_goal(
    goal_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Archive a learning goal."""
    service = GoalService(db)
    await service.delete_goal(goal_id, user.id)
    return {"message": "Goal archived"}
