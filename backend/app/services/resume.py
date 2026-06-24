"""Resume service - determines the user's current learning state."""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.datetime import to_iso_string
from app.models.goal import LearningGoal

logger = structlog.get_logger()


class ResumeService:
    """Determine what to show on the user's resume/home page."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_resume(self, user_id: str) -> dict[str, object]:
        """Get the resume state for a user.

        Priority:
        1. Running task (generating)
        2. Draft path (review)
        3. Active path (active)
        4. Completed path (completed)
        5. Empty
        """
        # Get the most recent non-archived goal
        result = await self.db.execute(
            select(LearningGoal)
            .where(
                LearningGoal.user_id == user_id,
                LearningGoal.status.notin_(["archived", "draft"]),
            )
            .order_by(LearningGoal.updated_at.desc())
            .limit(1)
        )
        goal = result.scalar_one_or_none()

        if not goal:
            return {"type": "empty"}

        # Check for generating state
        if goal.status in ("clarifying", "diagnosing", "planning") and goal.active_task_id:
            return {
                "type": "generating",
                "goal_id": goal.id,
                "task_id": goal.active_task_id,
                "goal_title": goal.title,
                "progress": 45,
                "stage": self._get_stage_label(goal.status),
                "message": self._get_stage_message(goal.status),
            }

        # Check for review state (path generated but not activated)
        if goal.status == "ready" and goal.current_path_id:
            return {
                "type": "review",
                "goal_id": goal.id,
                "path_id": goal.current_path_id,
                "path_title": goal.title,
                "version": 1,
                "total_nodes": 0,  # Will be populated from path data
                "estimated_minutes": 0,
            }

        # Check for active state
        if goal.status == "active" and goal.current_path_id:
            return {
                "type": "active",
                "path_id": goal.current_path_id,
                "path_title": goal.title,
                "current_node_id": "",
                "current_node_title": "",
                "completed_nodes": 0,
                "total_nodes": 0,
                "progress": 0,
                "last_active_at": to_iso_string(goal.updated_at),
            }

        # Check for completed state
        if goal.status == "completed":
            return {
                "type": "completed",
                "path_id": goal.current_path_id or "",
                "path_title": goal.title,
                "completed_nodes": 0,
                "total_nodes": 0,
                "completed_at": to_iso_string(goal.updated_at),
                "mastery": 0,
            }

        return {"type": "empty"}

    def _get_stage_label(self, status: str) -> str:
        """Get a human-readable stage label."""
        labels = {
            "clarifying": "目标澄清",
            "diagnosing": "能力诊断",
            "planning": "路径规划",
        }
        return labels.get(status, "处理中")

    def _get_stage_message(self, status: str) -> str:
        """Get a stage-specific message."""
        messages = {
            "clarifying": "智能体正在澄清细节问题...",
            "diagnosing": "正在分析诊断结果...",
            "planning": "正在梳理知识节点连线...",
        }
        return messages.get(status, "处理中...")
