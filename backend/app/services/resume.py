"""Resume service - determines the user's current learning state."""

from __future__ import annotations

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.datetime import to_iso_string
from app.models.goal import LearningGoal
from app.models.path import LearningNode, LearningPath
from app.models.progress import LearningProgress

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

        # Compute path stats if a path exists
        path_stats = await self._get_path_stats(goal.current_path_id, user_id) if goal.current_path_id else {}

        # Check for review state (path generated but not activated)
        if goal.status == "ready" and goal.current_path_id:
            return {
                "type": "review",
                "goal_id": goal.id,
                "path_id": goal.current_path_id,
                "path_title": goal.title,
                "version": 1,
                "total_nodes": path_stats.get("total_nodes", 0),
                "estimated_minutes": path_stats.get("estimated_minutes", 0),
            }

        # Check for active state
        if goal.status == "active" and goal.current_path_id:
            current_node = path_stats.get("current_node")
            current_node_dict = current_node if isinstance(current_node, dict) else None
            return {
                "type": "active",
                "path_id": goal.current_path_id,
                "path_title": goal.title,
                "current_node_id": current_node_dict["id"] if current_node_dict else "",
                "current_node_title": current_node_dict["title"] if current_node_dict else "",
                "completed_nodes": path_stats.get("completed_nodes", 0),
                "total_nodes": path_stats.get("total_nodes", 0),
                "progress": path_stats.get("progress", 0),
                "last_active_at": to_iso_string(goal.updated_at),
            }

        # Check for completed state
        if goal.status == "completed":
            return {
                "type": "completed",
                "path_id": goal.current_path_id or "",
                "path_title": goal.title,
                "completed_nodes": path_stats.get("completed_nodes", 0),
                "total_nodes": path_stats.get("total_nodes", 0),
                "completed_at": to_iso_string(goal.updated_at),
                "mastery": path_stats.get("mastery", 0),
            }

        return {"type": "empty"}

    async def _get_path_stats(self, path_id: str, user_id: str) -> dict[str, object]:
        """Compute real path statistics from the database."""
        # Get active version
        path_result = await self.db.execute(select(LearningPath).where(LearningPath.id == path_id))
        path = path_result.scalar_one_or_none()
        if not path or not path.active_version_id:
            return {}

        version_id = path.active_version_id

        # Count total nodes
        total_result = await self.db.execute(
            select(func.count()).select_from(LearningNode).where(LearningNode.version_id == version_id)
        )
        total_nodes = total_result.scalar() or 0

        # Count completed nodes
        completed_result = await self.db.execute(
            select(func.count())
            .select_from(LearningProgress)
            .where(
                LearningProgress.user_id == user_id,
                LearningProgress.path_id == path_id,
                LearningProgress.status == "completed",
            )
        )
        completed_nodes = completed_result.scalar() or 0

        # Compute progress percentage
        progress = int((completed_nodes / total_nodes * 100) if total_nodes > 0 else 0)

        # Get estimated total minutes
        minutes_result = await self.db.execute(
            select(func.sum(LearningNode.estimated_minutes)).where(LearningNode.version_id == version_id)
        )
        estimated_minutes = minutes_result.scalar() or 0

        # Get current node (first non-completed node)
        current_node = None
        nodes_result = await self.db.execute(
            select(LearningNode).where(LearningNode.version_id == version_id).order_by(LearningNode.node_order)
        )
        for node in nodes_result.scalars().all():
            prog_result = await self.db.execute(
                select(LearningProgress).where(
                    LearningProgress.user_id == user_id,
                    LearningProgress.path_id == path_id,
                    LearningProgress.node_id == node.id,
                )
            )
            prog = prog_result.scalar_one_or_none()
            if not prog or prog.status != "completed":
                current_node = {"id": node.id, "title": node.title}
                break

        # Compute average mastery
        mastery_result = await self.db.execute(
            select(func.avg(LearningProgress.mastery)).where(
                LearningProgress.user_id == user_id,
                LearningProgress.path_id == path_id,
            )
        )
        mastery = round(mastery_result.scalar() or 0, 1)

        return {
            "total_nodes": total_nodes,
            "completed_nodes": completed_nodes,
            "progress": progress,
            "estimated_minutes": estimated_minutes,
            "current_node": current_node,
            "mastery": mastery,
        }

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
