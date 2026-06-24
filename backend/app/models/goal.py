"""Learning goal model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

if TYPE_CHECKING:
    from datetime import datetime


def generate_uuid() -> str:
    return str(uuid.uuid4())


class LearningGoal(Base):
    """Learning goal created by a user."""

    __tablename__ = "learning_goals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    raw_description: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    weekly_hours: Mapped[int | None] = mapped_column(nullable=True)
    preferences: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    use_diagnostic: Mapped[bool] = mapped_column(default=True)
    use_knowledge_base: Mapped[bool] = mapped_column(default=False)
    content_language: Mapped[str] = mapped_column(String(10), default="zh")
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="draft",
        index=True,
    )
    active_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    current_path_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# Valid state transitions
GOAL_STATE_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"clarifying", "diagnosing", "planning", "failed", "archived"},
    "clarifying": {"diagnosing", "planning", "failed", "archived"},
    "diagnosing": {"planning", "failed", "archived"},
    "planning": {"ready", "failed", "archived"},
    "ready": {"active", "archived"},
    "active": {"completed", "failed", "archived"},
    "completed": {"archived"},
    "failed": {"draft", "archived"},  # Can retry from failed
    "archived": set(),
}


def validate_goal_transition(current: str, target: str) -> bool:
    """Validate that a goal state transition is allowed."""
    allowed = GOAL_STATE_TRANSITIONS.get(current, set())
    return target in allowed
