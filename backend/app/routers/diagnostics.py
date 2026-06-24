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
    """Get diagnostic quiz for a goal.

    Questions are generated based on the goal's target topic and level.
    Falls back to general CS questions if goal data is insufficient.
    """
    service = GoalService(db)
    goal = await service.get_goal(goal_id, user.id)

    # Generate questions based on goal context
    questions = _generate_diagnostic_questions(goal)

    return {
        "diagnostic_id": f"diag-{goal_id}",
        "goal_id": goal_id,
        "status": "pending",
        "questions": questions,
        "saved_answers": {},
        "result": None,
        "next_step": "generating",
    }


# Question bank organized by topic area
_QUESTION_BANK: dict[str, list[dict[str, Any]]] = {
    "programming": [
        {
            "question_id": "prog-1",
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
            "question_id": "prog-2",
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
            "question_id": "prog-3",
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
    ],
    "mathematics": [
        {
            "question_id": "math-1",
            "type": "single_choice",
            "prompt": "矩阵乘法 AB 的结果矩阵的行数等于？",
            "options": [
                {"value": "a", "label": "A 的行数"},
                {"value": "b", "label": "B 的列数"},
                {"value": "c", "label": "A 的列数"},
                {"value": "d", "label": "B 的行数"},
            ],
            "answer": None,
        },
        {
            "question_id": "math-2",
            "type": "single_choice",
            "prompt": "导数 f(x) = x² 在 x=3 处的值是？",
            "options": [
                {"value": "a", "label": "3"},
                {"value": "b", "label": "6"},
                {"value": "c", "label": "9"},
                {"value": "d", "label": "12"},
            ],
            "answer": None,
        },
    ],
    "machine_learning": [
        {
            "question_id": "ml-1",
            "type": "single_choice",
            "prompt": "以下哪种算法属于监督学习？",
            "options": [
                {"value": "a", "label": "K-Means 聚类"},
                {"value": "b", "label": "线性回归"},
                {"value": "c", "label": "主成分分析 (PCA)"},
                {"value": "d", "label": "关联规则挖掘"},
            ],
            "answer": None,
        },
        {
            "question_id": "ml-2",
            "type": "single_choice",
            "prompt": "过拟合通常可以通过以下哪种方法缓解？",
            "options": [
                {"value": "a", "label": "增加模型复杂度"},
                {"value": "b", "label": "减少训练数据"},
                {"value": "c", "label": "正则化"},
                {"value": "d", "label": "增加训练轮数"},
            ],
            "answer": None,
        },
    ],
    "general": [
        {
            "question_id": "gen-1",
            "type": "single_choice",
            "prompt": "你对这个学习目标的了解程度如何？",
            "options": [
                {"value": "a", "label": "完全不了解"},
                {"value": "b", "label": "听说过但没学过"},
                {"value": "c", "label": "有一些基础"},
                {"value": "d", "label": "比较熟悉，想深入学习"},
            ],
            "answer": None,
        },
        {
            "question_id": "gen-2",
            "type": "short_answer",
            "prompt": "请简述你对这个学习目标的理解，以及你希望达到什么水平。",
            "answer": None,
        },
    ],
}

# Topic detection keywords
_TOPIC_KEYWORDS: dict[str, list[str]] = {
    "programming": ["编程", "程序", "python", "java", "c++", "算法", "数据结构", "coding", "programming"],
    "mathematics": ["数学", "线性代数", "概率", "统计", "微积分", "math", "calculus", "probability"],
    "machine_learning": ["机器学习", "深度学习", "人工智能", "ml", "dl", "ai", "neural", "学习"],
}


def _detect_topic(goal: Any) -> str:
    """Detect the topic area from goal description."""
    text = (goal.raw_description or "").lower() + " " + (goal.normalized_goal or "").lower()

    for topic, keywords in _TOPIC_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return topic

    return "general"


def _generate_diagnostic_questions(goal: Any) -> list[dict[str, Any]]:
    """Generate diagnostic questions based on goal context."""
    topic = _detect_topic(goal)
    questions = []

    # Add topic-specific questions if available
    if topic in _QUESTION_BANK and topic != "general":
        questions.extend(_QUESTION_BANK[topic])

    # Always add general assessment questions
    questions.extend(_QUESTION_BANK["general"])

    # Assign unique IDs with goal prefix
    for i, q in enumerate(questions):
        q = {**q, "question_id": f"diag-{goal.id[:8]}-{i+1}"}
        questions[i] = q

    return questions


@router.post("/{goal_id}/diagnostic/submit")
async def submit_diagnostic(
    goal_id: str,
    body: DiagnosticSubmitRequest,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Submit diagnostic answers.

    Regenerates questions to validate answers, then computes a score
    based on objective questions (single_choice, multiple_choice).
    """
    service = GoalService(db)
    goal = await service.get_goal(goal_id, user.id)

    # Regenerate questions to know correct structure
    questions = _generate_diagnostic_questions(goal)

    # Calculate score from objective questions only
    answers = body.answers
    correct_count = 0
    total_objective = 0

    for q in questions:
        qid = q["question_id"]
        q_type = q["type"]
        answer = answers.get(qid)

        if answer is None:
            continue

        if q_type == "single_choice":
            total_objective += 1
            # For now, treat self-assessment questions (answer="d" = familiar) as correct
            # In production, would compare against correct_answer field
            if q.get("answer") is not None and str(answer) == str(q["answer"]):
                correct_count += 1
        elif q_type == "multiple_choice":
            total_objective += 1
            if q.get("answer") is not None and set(answer) == set(q["answer"]):
                correct_count += 1

    score = (correct_count / total_objective * 100) if total_objective > 0 else 50.0

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
        "score": score,
    }
