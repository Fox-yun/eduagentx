"""Clarification API endpoints with persistent storage."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_deps import require_learning_user
from app.core.database import get_db
from app.core.errors import ApiError
from app.models.clarification import ClarificationAnswer, ClarificationQuestion, ClarificationSet
from app.models.user import User
from app.services.goal import GoalService

router = APIRouter()


class ClarificationAnswerRequest(BaseModel):
    answers: dict[str, str | int | bool | list[str]]


DEFAULT_QUESTIONS = [
    {
        "question_type": "single_choice",
        "prompt": "您目前的技术水平如何？",
        "required": True,
        "options": [
            {"value": "beginner", "label": "初学者 - 刚开始学习"},
            {"value": "intermediate", "label": "中级 - 有一定基础"},
            {"value": "advanced", "label": "高级 - 有丰富经验"},
        ],
        "question_order": 1,
    },
    {
        "question_type": "multiple_choice",
        "prompt": "您希望重点学习哪些方面？",
        "required": True,
        "options": [
            {"value": "theory", "label": "理论基础"},
            {"value": "practice", "label": "实践项目"},
            {"value": "interview", "label": "面试准备"},
            {"value": "research", "label": "学术研究"},
        ],
        "question_order": 2,
    },
    {
        "question_type": "number",
        "prompt": "每周预计投入多少小时？",
        "required": True,
        "min_value": 1,
        "max_value": 40,
        "question_order": 3,
    },
    {
        "question_type": "single_choice",
        "prompt": "您偏好哪种学习方式？",
        "required": True,
        "options": [
            {"value": "video", "label": "视频教程"},
            {"value": "text", "label": "文字教程"},
            {"value": "interactive", "label": "交互式练习"},
            {"value": "project", "label": "项目驱动"},
        ],
        "question_order": 4,
    },
]


@router.get("/{goal_id}/clarifications")
async def get_clarifications(
    goal_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get clarification questions for a goal."""
    service = GoalService(db)
    await service.get_goal(goal_id, user.id)

    result = await db.execute(
        select(ClarificationSet).where(
            ClarificationSet.goal_id == goal_id,
            ClarificationSet.status == "active",
        )
    )
    clar_set = result.scalar_one_or_none()

    if not clar_set:
        clar_set = ClarificationSet(goal_id=goal_id)
        db.add(clar_set)
        await db.flush()

        for q_data in DEFAULT_QUESTIONS:
            question = ClarificationQuestion(
                set_id=clar_set.id,
                question_type=q_data["question_type"],
                prompt=q_data["prompt"],
                required=q_data.get("required", True),
                options=q_data.get("options"),
                min_value=q_data.get("min_value"),
                max_value=q_data.get("max_value"),
                question_order=q_data.get("question_order", 0),
            )
            db.add(question)
        await db.flush()

    questions_result = await db.execute(
        select(ClarificationQuestion)
        .where(ClarificationQuestion.set_id == clar_set.id)
        .order_by(ClarificationQuestion.question_order)
    )
    questions = list(questions_result.scalars().all())

    answers_result = await db.execute(select(ClarificationAnswer).where(ClarificationAnswer.goal_id == goal_id))
    answers = {a.question_id: json.loads(a.answer_value) for a in answers_result.scalars().all()}

    return {
        "questions": [
            {
                "question_id": q.id,
                "type": q.question_type,
                "prompt": q.prompt,
                "required": q.required,
                "options": q.options,
                "min": q.min_value,
                "max": q.max_value,
                "answer": answers.get(q.id),
            }
            for q in questions
        ],
        "answers_history": answers if answers else None,
    }


@router.post("/{goal_id}/clarifications")
async def submit_clarifications(
    goal_id: str,
    body: ClarificationAnswerRequest,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Submit clarification answers."""
    service = GoalService(db)
    goal = await service.get_goal(goal_id, user.id)

    result = await db.execute(
        select(ClarificationSet).where(
            ClarificationSet.goal_id == goal_id,
            ClarificationSet.status == "active",
        )
    )
    clar_set = result.scalar_one_or_none()

    if not clar_set:
        raise ApiError(code="CLARIFICATION_NOT_FOUND", message="Clarification set not found", status_code=404)

    questions_result = await db.execute(
        select(ClarificationQuestion).where(ClarificationQuestion.set_id == clar_set.id)
    )
    questions = {q.id: q for q in questions_result.scalars().all()}

    for question_id, answer_value in body.answers.items():
        if question_id not in questions:
            continue

        existing_result = await db.execute(
            select(ClarificationAnswer).where(
                ClarificationAnswer.question_id == question_id,
                ClarificationAnswer.goal_id == goal_id,
            )
        )
        existing = existing_result.scalar_one_or_none()

        if existing:
            existing.answer_value = json.dumps(answer_value)
        else:
            answer = ClarificationAnswer(
                question_id=question_id,
                goal_id=goal_id,
                answer_value=json.dumps(answer_value),
            )
            db.add(answer)

    if goal.status == "draft":
        await service.transition_goal(goal_id, user.id, "diagnosing")

    await db.flush()

    return {
        "next_step": "diagnostic",
        "active_task_id": None,
    }
