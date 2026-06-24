"""Diagnostic API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_deps import require_learning_user
from app.core.database import get_db
from app.models.user import User
from app.services.goal import GoalService
from app.services.task import TaskService

router = APIRouter()


class DiagnosticSubmitRequest(BaseModel):
    answers: dict[str, str | list[str]]


@router.get("/{goal_id}/diagnostic")
async def get_diagnostic(
    goal_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get diagnostic quiz for a goal."""
    service = GoalService(db)
    await service.get_goal(goal_id, user.id)

    # Generate diagnostic questions
    questions = [
        {
            "question_id": "diag-1",
            "type": "single_choice",
            "prompt": "以下哪个数据结构常用于实现广度优先搜索？",
            "options": [
                {"value": "a", "label": "栈 (Stack)"},
                {"value": "b", "label": "队列 (Queue)"},
                {"value": "c", "label": "哈希表 (Hash Table)"},
                {"value": "d", "label": "二叉树 (Binary Tree)"},
            ],
            "answer": None,
        },
        {
            "question_id": "diag-2",
            "type": "single_choice",
            "prompt": "时间复杂度 O(n log n) 通常对应哪种排序算法？",
            "options": [
                {"value": "a", "label": "冒泡排序"},
                {"value": "b", "label": "快速排序"},
                {"value": "c", "label": "插入排序"},
                {"value": "d", "label": "选择排序"},
            ],
            "answer": None,
        },
        {
            "question_id": "diag-3",
            "type": "multiple_choice",
            "prompt": "以下哪些是 Python 的内置数据类型？",
            "options": [
                {"value": "a", "label": "list"},
                {"value": "b", "label": "array"},
                {"value": "c", "label": "dict"},
                {"value": "d", "label": "set"},
            ],
            "answer": None,
        },
        {
            "question_id": "diag-4",
            "type": "short_answer",
            "prompt": "请简述什么是递归，并举一个例子。",
            "answer": None,
        },
    ]

    return {
        "diagnostic_id": f"diag-{goal_id}",
        "goal_id": goal_id,
        "status": "pending",
        "questions": questions,
        "saved_answers": {},
        "result": None,
        "next_step": "generating",
    }


@router.post("/{goal_id}/diagnostic/submit")
async def submit_diagnostic(
    goal_id: str,
    body: DiagnosticSubmitRequest,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Submit diagnostic answers."""
    service = GoalService(db)
    goal = await service.get_goal(goal_id, user.id)

    # Calculate score (simplified)
    answers = body.answers
    correct_count = 0
    total_objective = 2  # Only count objective questions

    if answers.get("diag-1") == "b":
        correct_count += 1
    if answers.get("diag-2") == "b":
        correct_count += 1

    (correct_count / total_objective) * 100 if total_objective > 0 else 0

    # Create a path generation task
    task_service = TaskService(db)
    task = await task_service.create_task(
        user_id=user.id,
        task_type="learning_path_generation",
        target_type="goal",
        target_id=goal_id,
    )

    # Update goal status and task ID
    if goal.status not in ("planning", "ready", "active"):
        await service.transition_goal(goal_id, user.id, "planning", task_id=task.id)
    else:
        goal.active_task_id = task.id
        await db.flush()

    return {
        "next_step": "generating",
        "active_task_id": task.id,
    }
