"""Diagnostic API endpoints with real scoring."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_deps import require_learning_user
from app.core.database import get_db
from app.models.diagnostic import DiagnosticAnswer, DiagnosticAttempt, DiagnosticResult
from app.models.user import User
from app.services.diagnostic_scoring import (
    score_multiple_choice,
    score_single_choice,
    score_true_false,
)
from app.services.goal import GoalService
from app.services.task import TaskService

router = APIRouter()


# ---------- Request/Response schemas ----------


class AnswerSubmitItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_id: str
    answer: Any = None  # str for single_choice, list[str] for multiple_choice, str for short_answer


class DiagnosticSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attempt_id: str
    answers: list[AnswerSubmitItem]


class QuestionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_id: str
    question_type: str
    prompt: str
    options: list[dict[str, str]] | None = None
    dimension: str | None = None
    max_score: float
    required: bool


class DiagnosticResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    diagnostic_id: str
    goal_id: str
    attempt_id: str
    status: str
    questions: list[QuestionResponse]
    saved_answers: dict[str, Any]
    result: dict[str, Any] | None
    next_step: str | None


# ---------- Question bank ----------

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
            "correct_answer": "b",
            "dimension": "algorithms",
            "max_score": 10,
            "required": True,
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
            "correct_answer": "b",
            "dimension": "algorithms",
            "max_score": 10,
            "required": True,
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
            "correct_answer": ["a", "c", "d"],
            "dimension": "programming_fundamentals",
            "max_score": 10,
            "required": True,
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
            "correct_answer": "a",
            "dimension": "linear_algebra",
            "max_score": 10,
            "required": True,
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
            "correct_answer": "b",
            "dimension": "calculus",
            "max_score": 10,
            "required": True,
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
            "correct_answer": "b",
            "dimension": "ml_fundamentals",
            "max_score": 10,
            "required": True,
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
            "correct_answer": "c",
            "dimension": "ml_fundamentals",
            "max_score": 10,
            "required": True,
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
            "correct_answer": None,  # Self-assessment — no right answer
            "dimension": "self_assessment",
            "max_score": 0,
            "required": True,
        },
        {
            "question_id": "gen-2",
            "type": "short_answer",
            "prompt": "请简述你对这个学习目标的理解，以及你希望达到什么水平。",
            "correct_answer": None,
            "rubric": "评估用户对目标的理解程度、学习动机的明确性和期望水平的合理性",
            "dimension": "self_assessment",
            "max_score": 10,
            "required": True,
        },
    ],
}

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


def _generate_diagnostic_questions(
    goal: Any,
    profile_context: Any | None = None,
) -> list[dict[str, Any]]:
    """Generate diagnostic questions based on goal context and learner profile.

    Phase 3.6-F: When a learner profile is available, the question selection
    is adjusted:
      - knowledge_depth < 0.4 → include more fundamental questions
      - knowledge_depth > 0.7 → include more advanced/comprehensive questions
      - learning_pace == 'slow' → include step-by-step guidance hints
    """
    topic = _detect_topic(goal)
    questions: list[dict[str, Any]] = []

    if topic in _QUESTION_BANK and topic != "general":
        # Phase 3.6-F: Profile-aware question selection
        topic_questions = list(_QUESTION_BANK[topic])

        if profile_context is not None:
            # Weak foundation: keep all basic questions, add self-assessment first
            kd = profile_context.dimensions.get("knowledge_depth")
            kd_value = kd.value if kd else None

            if isinstance(kd_value, (int, float)) and kd_value < 0.4:
                # For weak foundation, ensure all topic questions are included
                # (they are fundamental) and add a note to the prompt
                for q in topic_questions:
                    q = dict(q)
                    q["prompt"] = f"【基础题】{q['prompt']}"
                    questions.append(q)
            elif isinstance(kd_value, (int, float)) and kd_value > 0.7:
                # For strong foundation, mark as comprehensive
                for q in topic_questions:
                    q = dict(q)
                    q["prompt"] = f"【综合题】{q['prompt']}"
                    questions.append(q)
            else:
                questions.extend(topic_questions)

            # Slow pace: add step-by-step hint to short_answer questions (topic only here;
            # general questions are handled below after they are added)
        else:
            questions.extend(topic_questions)

    questions.extend(_QUESTION_BANK["general"])

    # Phase 3.6-F: Apply slow pace hint to ALL short_answer questions
    # (both topic and general) after all questions are assembled
    if profile_context is not None:
        lp = profile_context.dimensions.get("learning_pace")
        if lp and lp.value == "slow":
            for i, q in enumerate(questions):
                if q.get("type") == "short_answer":
                    questions[i] = {**q, "prompt": q["prompt"] + "\n（请分步骤作答，逐步说明你的思路。）"}

    for i, q in enumerate(questions):
        q = {**q, "question_id": f"diag-{goal.id[:8]}-{i + 1}"}
        questions[i] = q

    return questions


def _question_to_public(q: dict[str, Any]) -> QuestionResponse:
    """Convert a question dict to public response (no correct_answer or rubric)."""
    return QuestionResponse(
        question_id=q["question_id"],
        question_type=q["type"],
        prompt=q["prompt"],
        options=q.get("options"),
        dimension=q.get("dimension"),
        max_score=float(q.get("max_score", 10)),
        required=q.get("required", True),
    )


# ---------- Endpoints ----------


@router.get("/{goal_id}/diagnostic")
async def get_diagnostic(
    goal_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get diagnostic quiz for a goal.

    Creates a draft attempt if none exists.
    Returns questions without correct_answer or rubric.
    """
    service = GoalService(db)
    goal = await service.get_goal(goal_id, user.id)

    # Phase 3.6-F: Load learner profile for personalised diagnostic questions
    profile_context = None
    try:
        from app.services.profile_context import load_learner_profile_context

        profile_context = await load_learner_profile_context(db, user_id=user.id)
    except Exception as e:
        import structlog

        structlog.get_logger().warning("profile_load_failed_for_diagnostic", error=str(e))

    questions = _generate_diagnostic_questions(goal, profile_context)

    # Find or create draft attempt
    result = await db.execute(
        select(DiagnosticAttempt)
        .where(
            DiagnosticAttempt.goal_id == goal_id,
            DiagnosticAttempt.user_id == user.id,
            DiagnosticAttempt.status.in_(["draft", "submitted", "grading"]),
        )
        .order_by(DiagnosticAttempt.created_at.desc())
        .limit(1)
    )
    attempt = result.scalar_one_or_none()

    if not attempt:
        attempt = DiagnosticAttempt(
            id=str(uuid.uuid4()),
            diagnostic_id=f"diag-{goal_id}",
            goal_id=goal_id,
            user_id=user.id,
            status="draft",
        )
        db.add(attempt)
        await db.flush()
        await db.commit()

    # Load saved answers from existing diagnostic answers
    saved_answers: dict[str, Any] = {}
    if attempt.status in ("submitted", "grading"):
        answers_result = await db.execute(select(DiagnosticAnswer).where(DiagnosticAnswer.attempt_id == attempt.id))
        for ans in answers_result.scalars().all():
            saved_answers[ans.question_id] = ans.answer

    return {
        "diagnostic_id": f"diag-{goal_id}",
        "goal_id": goal_id,
        "attempt_id": attempt.id,
        "status": attempt.status,
        "questions": [_question_to_public(q) for q in questions],
        "saved_answers": saved_answers,
        "result": None,
        "next_step": "generating" if attempt.status in ("submitted", "grading", "completed") else "diagnostic",
    }


@router.post("/{goal_id}/diagnostic/submit")
async def submit_diagnostic(
    goal_id: str,
    body: DiagnosticSubmitRequest,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Submit diagnostic answers.

    Scores objective questions synchronously, then creates a grading
    task for short-answer LLM evaluation.
    """
    # Load attempt with FOR UPDATE
    result = await db.execute(
        select(DiagnosticAttempt)
        .where(
            DiagnosticAttempt.id == body.attempt_id,
            DiagnosticAttempt.goal_id == goal_id,
            DiagnosticAttempt.user_id == user.id,
        )
        .with_for_update()
    )
    attempt = result.scalar_one_or_none()
    if not attempt:
        from app.core.errors import ApiError

        raise ApiError(code="ATTEMPT_NOT_FOUND", message="Attempt not found", status_code=404)

    if attempt.status not in ("draft", "submitted"):
        from app.core.errors import ApiError

        raise ApiError(
            code="INVALID_ATTEMPT_STATUS",
            message=f"Attempt is in state '{attempt.status}', cannot submit",
            status_code=400,
        )

    # Load goal and regenerate questions for correct answers
    goal_service = GoalService(db)
    goal = await goal_service.get_goal(goal_id, user.id)

    # Phase 3.6-F: Load profile context for consistent question generation
    profile_context = None
    try:
        from app.services.profile_context import load_learner_profile_context

        profile_context = await load_learner_profile_context(db, user_id=user.id)
    except Exception:
        pass

    questions = _generate_diagnostic_questions(goal, profile_context)
    q_map: dict[str, dict[str, Any]] = {q["question_id"]: q for q in questions}

    # Save answers and score objective questions
    now_utc = datetime.now(UTC)
    scored_answers: list[dict[str, Any]] = []

    for item in body.answers:
        q = q_map.get(item.question_id)
        if not q:
            from app.core.errors import ApiError

            raise ApiError(
                code="QUESTION_NOT_FOUND",
                message=f"Question '{item.question_id}' not found in diagnostic",
                status_code=400,
            )

        q_type = q["type"]
        correct = q.get("correct_answer")
        max_score = Decimal(str(q.get("max_score", 10)))

        # Score objective questions
        if q_type == "single_choice" and correct is not None:
            sa = score_single_choice(str(item.answer or ""), str(correct), max_score)
        elif q_type == "multiple_choice" and correct is not None:
            user_ans = list(item.answer) if isinstance(item.answer, list) else []
            sa = score_multiple_choice(user_ans, list(correct), max_score)
        elif q_type == "true_false" and correct is not None:
            sa = score_true_false(bool(item.answer), bool(correct), max_score)
        else:
            # Short answer or self-assessment — mark as ungraded (LLM will score)
            sa = None

        answer_record = DiagnosticAnswer(
            id=str(uuid.uuid4()),
            attempt_id=attempt.id,
            question_id=item.question_id,
            answer=json.dumps(item.answer) if not isinstance(item.answer, str) else item.answer,
            score=float(sa.score) if sa else 0.0,
            max_score=float(max_score),
            is_correct=sa.is_correct if sa else None,
            feedback=sa.feedback if sa else None,
            grading_source=sa.grading_source if sa else "llm",
            grading_status=sa.grading_status if sa else "provisional",
        )
        db.add(answer_record)
        if sa:
            scored_answers.append(
                {
                    "question_id": item.question_id,
                    "score": float(sa.score),
                    "max_score": float(max_score),
                    "is_correct": sa.is_correct,
                    "grading_source": sa.grading_source,
                    "grading_status": sa.grading_status,
                }
            )

    # Update attempt
    attempt.status = "grading"
    attempt.submitted_at = now_utc
    await db.flush()

    # Create grading task
    task_service = TaskService(db)
    grading_task = await task_service.create_task(
        user_id=user.id,
        task_type="diagnostic_grading",
        target_type="attempt",
        target_id=attempt.id,
        idempotency_key=f"diagnostic-grade:{attempt.id}",
    )

    await db.commit()

    return {
        "attempt_id": attempt.id,
        "status": "grading",
        "task_id": grading_task.id,
        "scored_questions": scored_answers,
    }


@router.get("/{goal_id}/diagnostic/result")
async def get_diagnostic_result(
    goal_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get the latest diagnostic result for a goal."""
    result = await db.execute(
        select(DiagnosticAttempt)
        .where(
            DiagnosticAttempt.goal_id == goal_id,
            DiagnosticAttempt.user_id == user.id,
        )
        .order_by(DiagnosticAttempt.created_at.desc())
        .limit(1)
    )
    attempt = result.scalar_one_or_none()
    if not attempt:
        from app.core.errors import ApiError

        raise ApiError(code="ATTEMPT_NOT_FOUND", message="No diagnostic attempt found", status_code=404)

    # Load result
    result_row = None
    if attempt.status == "completed":
        r = await db.execute(select(DiagnosticResult).where(DiagnosticResult.attempt_id == attempt.id))
        result_row = r.scalar_one_or_none()

    # Load answers
    answers_res = await db.execute(select(DiagnosticAnswer).where(DiagnosticAnswer.attempt_id == attempt.id))
    answers = answers_res.scalars().all()
    question_results = [
        {
            "question_id": a.question_id,
            "score": a.score,
            "max_score": a.max_score,
            "is_correct": a.is_correct,
            "grading_source": a.grading_source,
            "grading_status": a.grading_status,
            "feedback": a.feedback,
        }
        for a in answers
    ]

    return {
        "attempt_id": attempt.id,
        "status": attempt.status,
        "grading_quality": attempt.grading_quality,
        "result": {
            "total_score": result_row.total_score if result_row else 0,
            "percentage": result_row.percentage if result_row else 0,
            "dimension_scores": result_row.dimension_scores if result_row else {},
            "readiness_level": result_row.readiness_level if result_row else None,
            "grading_quality": result_row.grading_quality if result_row else attempt.grading_quality,
        }
        if result_row
        else None,
        "questions": question_results,
    }
