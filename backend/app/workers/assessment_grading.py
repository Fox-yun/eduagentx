"""Assessment grading worker for short-answer questions.

Uses the two-phase transaction pattern:
  Transaction A: FOR UPDATE attempt, verify status, mark grading -> commit
  (no txn): Call LLM for short-answer batch grading
  Transaction B: FOR UPDATE attempt, save LLM scores, mark completed -> commit
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import select

from app.models.unit import AssessmentAnswer, AssessmentAttempt, AssessmentQuestion
from app.services.answer_scoring import PROVISIONAL_FEEDBACK, PROVISIONAL_WEIGHT, _d
from app.services.llm import llm_json
from app.workers.task_handlers import register_handler
from app.workers.task_runtime import update_task_status

logger = structlog.get_logger()

SHORT_ANSWER_GRADING_SYSTEM_PROMPT = """你是一个教育评估判分智能体。请对学生的简答题答案进行评分。

评分标准：
- 80-100分：答案准确、完整、有深度
- 60-79分：答案基本正确，但不够完整
- 40-59分：答案部分正确，有明显遗漏
- 0-39分：答案错误或过于简略

请以 JSON 格式输出每道题的评分，index 从 0 开始：
{
  "grades": [
    {"index": 0, "score": 75, "feedback": "具体评价和建议"}
  ]
}"""


@register_handler("assessment_grading")
async def execute_assessment_grading(db: Any, task: Any) -> dict[str, Any]:
    """Grade short-answer questions in an assessment attempt."""
    attempt_id = task.target_id
    metadata = task.target_metadata or {}
    assessment_id = metadata.get("assessment_id", "")

    await update_task_status(db, task.id, "running", progress=5, stage="loading", message="正在加载评分上下文...")

    # ==================================================================
    # Transaction A: Load attempt FOR UPDATE, mark grading
    # ==================================================================
    attempt_result = await db.execute(
        select(AssessmentAttempt).where(AssessmentAttempt.id == attempt_id).with_for_update()
    )
    attempt: AssessmentAttempt | None = attempt_result.scalar_one_or_none()
    if not attempt:
        raise ValueError(f"Attempt {attempt_id} not found")
    if attempt.status == "completed":
        return {"attempt_id": attempt_id, "status": "completed", "graded_count": 0}

    attempt.status = "grading"
    await update_task_status(db, task.id, "running", progress=15, stage="grading", message="正在调用大语言模型评分...")
    await db.commit()

    # ==================================================================
    # Load short-answer questions and answers for LLM grading
    # ==================================================================
    questions_result = await db.execute(
        select(AssessmentQuestion).where(
            AssessmentQuestion.assessment_id == (assessment_id or attempt.assessment_id),
            AssessmentQuestion.question_type == "short_answer",
        ).order_by(AssessmentQuestion.question_order)
    )
    sa_questions: list[AssessmentQuestion] = list(questions_result.scalars().all())
    if not sa_questions:
        # No short-answer questions — nothing to grade
        await _finalize_attempt(db, attempt, task.id)
        return {"attempt_id": attempt_id, "status": "completed", "graded_count": 0}

    # Build (idx, prompt, answer) pairs for LLM
    sa_pairs: list[tuple[int, str, str]] = []
    sa_answer_map: dict[str, AssessmentAnswer] = {}
    for q in sa_questions:
        answer_result = await db.execute(
            select(AssessmentAnswer).where(
                AssessmentAnswer.attempt_id == attempt_id,
                AssessmentAnswer.question_id == q.id,
            )
        )
        ans = answer_result.scalar_one_or_none()
        if ans and ans.answer_value:
            sa_pairs.append((q.question_order, q.prompt, ans.answer_value))
            sa_answer_map[q.id] = ans

    if not sa_pairs:
        await _finalize_attempt(db, attempt, task.id)
        return {"attempt_id": attempt_id, "status": "completed", "graded_count": 0}

    grading_source = "llm"
    grading_status = "graded"
    grades: dict[str, dict[str, Any]] = {}

    # ==================================================================
    # Outside transaction: LLM batch grading
    # ==================================================================
    try:
        questions_text = "\n\n".join(
            f"[题目{i}] {prompt}\n[学生答案] {answer}" for i, (_, prompt, answer) in enumerate(sa_pairs)
        )
        raw = await llm_json(
            SHORT_ANSWER_GRADING_SYSTEM_PROMPT,
            f"请对以下简答题答案进行评分：\n\n{questions_text}",
            temperature=0.2,
            max_tokens=2048,
        )
        llm_grades = raw.get("grades", [])
        for g in llm_grades:
            idx = g.get("index")
            if idx is not None and 0 <= idx < len(sa_pairs):
                q_order, _, _ = sa_pairs[idx]
                for q in sa_questions:
                    if q.question_order == q_order:
                        grades[q.id] = {"score": g.get("score", 0), "feedback": g.get("feedback", "")}
                        break

        await update_task_status(
            db, task.id, "running", progress=60, stage="saving", message="LLM 评分完成，正在保存..."
        )
    except Exception:
        logger.warning("llm_grading_fallback", attempt_id=attempt_id)
        grading_source = "fallback"
        grading_status = "provisional"
        for q in sa_questions:
            grades[q.id] = {"score": 50, "feedback": PROVISIONAL_FEEDBACK}

    # ==================================================================
    # Transaction B: FOR UPDATE, save scores, finalize
    # ==================================================================
    attempt_result_b = await db.execute(
        select(AssessmentAttempt).where(AssessmentAttempt.id == attempt_id).with_for_update()
    )
    attempt_b = attempt_result_b.scalar_one_or_none()
    if not attempt_b:
        raise ValueError(f"Attempt {attempt_id} not found on re-acquire")

    for q in sa_questions:
        grade = grades.get(q.id, {"score": 0, "feedback": ""})
        ans = sa_answer_map.get(q.id)
        if not ans:
            continue
        max_d = _d(q.max_score or 1.0)
        score_pct = max(0, min(100, grade.get("score", 0)))
        if grading_source == "fallback":
            points = float((max_d * PROVISIONAL_WEIGHT).quantize(_d("0.01")))
        else:
            points = float(max_d) * score_pct / 100.0
        ans.is_correct = score_pct >= 60
        ans.points_earned = points
        ans.grading_source = grading_source
        ans.grading_status = grading_status
        ans.feedback = grade.get("feedback", "") or ""

    await _finalize_attempt(db, attempt_b, task.id)

    return {
        "attempt_id": attempt_id,
        "status": "completed",
        "graded_count": len(sa_questions),
        "grading_source": grading_source,
        "grading_status": grading_status,
    }


async def _finalize_attempt(db: Any, attempt: AssessmentAttempt, task_id: str) -> None:
    """Calculate final score and mark attempt completed."""
    from sqlalchemy import func as sa_func

    # Aggregate scores from all answers
    agg_result = await db.execute(
        select(
            sa_func.coalesce(sa_func.sum(AssessmentAnswer.points_earned), 0).label("earned"),
            sa_func.coalesce(sa_func.sum(AssessmentAnswer.max_score), 0).label("max_possible"),
        ).where(AssessmentAnswer.attempt_id == attempt.id)
    )
    row = agg_result.one()
    earned = float(row.earned) if row.earned else 0
    max_possible = float(row.max_possible) if row.max_possible else 0

    attempt.score = (earned / max_possible * 100) if max_possible > 0 else 0
    attempt.passed = attempt.score >= 60
    attempt.status = "completed"
    attempt.grading_quality = "final"
    attempt.active_task_id = None
    attempt.submitted_at = attempt.submitted_at or __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    )

    await db.commit()
