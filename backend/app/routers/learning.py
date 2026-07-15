"""Authenticated learning-behaviour event API."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_deps import require_learning_user
from app.core.database import get_db
from app.models.user import User
from app.services.learning_behavior import record_learning_event

router = APIRouter()

LearningEventType = Literal[
    "node_opened",
    "resource_opened",
    "resource_completed",
    "resource_downloaded",
    "practice_started",
    "practice_completed",
    "tutor_question",
    "tutor_feedback",
]


class LearningEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path_id: str = Field(min_length=36, max_length=36)
    node_id: str | None = Field(default=None, min_length=36, max_length=36)
    event_type: LearningEventType
    resource_type: str | None = Field(default=None, max_length=40)
    duration_seconds: int | None = Field(default=None, ge=0, le=86400)
    client_event_id: str | None = Field(default=None, min_length=1, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime | None = None


@router.post("/events")
async def create_learning_event(
    body: LearningEventRequest,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    occurred_at = body.occurred_at or datetime.now(UTC)
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=UTC)

    event, profile_version, created = await record_learning_event(
        db,
        user_id=user.id,
        path_id=body.path_id,
        node_id=body.node_id,
        event_type=body.event_type,
        resource_type=body.resource_type,
        duration_seconds=body.duration_seconds,
        client_event_id=body.client_event_id,
        event_metadata=body.metadata,
        occurred_at=occurred_at,
    )
    await db.commit()
    return {
        "event_id": event.id,
        "created": created,
        "profile_version": profile_version,
    }


@router.get("/effectiveness/{path_id}")
async def get_effectiveness_report(
    path_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return an explainable, path-scoped learning effectiveness report."""
    from app.services.effectiveness import get_learning_effectiveness

    return await get_learning_effectiveness(db, user_id=user.id, path_id=path_id)
