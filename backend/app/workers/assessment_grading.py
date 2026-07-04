"""Assessment grading worker for short-answer questions.

Uses a three-phase pattern with separate DB sessions to ensure no
implicit transaction is held during the LLM call:

  Phase 1 (Session A): Load attempt/questions/answers, mark "grading", commit + close
  Phase 2 (no session): Call LLM for short-answer batch grading
  Phase 3 (Session B): FOR UPDATE attempt, save scores, finalize, commit + close
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select

from app.core.database import get_session_factory
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


@dataclass(frozen=True)
class GradingInput:
    """Immutable snapshot of short-answer data extracted from Session A.

    This is passed to the LLM call phase so no DB session is needed.
    """

    attempt_id: str
    assessment_id: str
    task_id: str
    sa_questions: list[dict[str, Any]]  # [{id, prompt, question_order, max_score}]
    sa_answers: dict[str, dict[str, Any]]  # {question_id: {answer_value, answer_id}}


@register_handler("assessment_grading")
async def execute_assessment_grading(db: Any, task: Any) -> dict[str, Any]:
    """Grade short-answer questions in an assessment attempt.

    Three-phase pattern:
      1. Session A: Read + mark "grading" + commit + close
      2. No session: LLM call
      3. Session B: FOR UPDATE + save + finalize + commit + close
    """
    attempt_id = task.target_id
    metadata = task.target_metadata or {}
    assessment_id = metadata.get("assessment_id", "")

    await update_task_status(db, task.id, "running", progress=5, stage="loading", message="正在加载评分上下文...")

    # ==================================================================
    # Phase 1: Session A — Load data, mark grading, commit, close
    # ==================================================================
    grading_input = await _phase_a_load_and_mark(task.id, attempt_id, assessment_id)

    # If no short-answer questions, finalize immediately in a fresh session
    if not grading_input.sa_questions:
        await _finalize_no_sa(task.id, attempt_id)
        return {"attempt_id": attempt_id, "status": "completed", "graded_count": 0}

    if not grading_input.sa_answers:
        await _finalize_no_sa(task.id, attempt_id)
        return {"attempt_id": attempt_id, "status": "completed", "graded_count": 0}

    # ==================================================================
    # Phase 2: No DB session — LLM batch grading
    # ==================================================================
    grading_source = "llm"
    grading_status = "graded"
    grades: dict[str, dict[str, Any]] = {}

    try:
        await update_task_status(
            db, task.id, "running", progress=20, stage="grading", message="正在调用大语言模型评分..."
        )

        questions_text = "\n\n".join(
            f"[题目{i}] {q['prompt']}\n[学生答案] {grading_input.sa_answers.get(q['id'], {}).get('answer_value', '')}"
            for i, q in enumerate(grading_input.sa_questions)
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
            if idx is not None and 0 <= idx < len(grading_input.sa_questions):
                q = grading_input.sa_questions[idx]
                grades[q["id"]] = {"score": g.get("score", 0), "feedback": g.get("feedback", "")}

        await update_task_status(
            db, task.id, "running", progress=60, stage="saving", message="LLM 评分完成，正在保存..."
        )
    except Exception:
        logger.warning("llm_grading_fallback", attempt_id=attempt_id)
        grading_source = "fallback"
        grading_status = "provisional"
        for q in grading_input.sa_questions:
            grades[q["id"]] = {"score": 50, "feedback": PROVISIONAL_FEEDBACK}

    # ==================================================================
    # Phase 3: Session B — FOR UPDATE, save scores, finalize
    # ==================================================================
    await _phase_b_save_and_finalize(
        task_id=task.id,
        attempt_id=attempt_id,
        grades=grades,
        grading_source=grading_source,
        grading_status=grading_status,
        sa_questions=grading_input.sa_questions,
        sa_answers=grading_input.sa_answers,
    )

    return {
        "attempt_id": attempt_id,
        "status": "completed",
        "graded_count": len(grading_input.sa_questions),
        "grading_source": grading_source,
        "grading_status": grading_status,
    }


async def _phase_a_load_and_mark(task_id: str, attempt_id: str, assessment_id: str) -> GradingInput:
    """Session A: Load attempt, mark grading, read questions/answers, commit, close.

    Returns an immutable GradingInput so the LLM phase needs no DB access.
    """
    factory = get_session_factory()
    async with factory() as db_a:
        # Load attempt FOR UPDATE
        attempt_result = await db_a.execute(
            select(AssessmentAttempt).where(AssessmentAttempt.id == attempt_id).with_for_update()
        )
        attempt: AssessmentAttempt | None = attempt_result.scalar_one_or_none()
        if not attempt:
            raise ValueError(f"Attempt {attempt_id} not found")
        if attempt.status == "completed":
            # Already completed — return empty input to short-circuit
            await db_a.commit()
            return GradingInput(
                attempt_id=attempt_id,
                assessment_id=assessment_id,
                task_id=task_id,
                sa_questions=[],
                sa_answers={},
            )

        attempt.status = "grading"
        await update_task_status(
            db_a, task_id, "running", progress=15, stage="grading", message="正在调用大语言模型评分..."
        )
        await db_a.commit()

        # After commit, read questions and answers (autobegin is fine — we'll commit+close)
        resolved_assessment_id = assessment_id or attempt.assessment_id
        questions_result = await db_a.execute(
            select(AssessmentQuestion)
            .where(
                AssessmentQuestion.assessment_id == resolved_assessment_id,
                AssessmentQuestion.question_type == "short_answer",
            )
            .order_by(AssessmentQuestion.question_order)
        )
        sa_question_rows: list[AssessmentQuestion] = list(questions_result.scalars().all())

        sa_questions: list[dict[str, Any]] = []
        sa_answers: dict[str, dict[str, Any]] = {}

        for q in sa_question_rows:
            answer_result = await db_a.execute(
                select(AssessmentAnswer).where(
                    AssessmentAnswer.attempt_id == attempt_id,
                    AssessmentAnswer.question_id == q.id,
                )
            )
            ans = answer_result.scalar_one_or_none()
            if ans and ans.answer_value:
                sa_questions.append(
                    {
                        "id": q.id,
                        "prompt": q.prompt,
                        "question_order": q.question_order,
                        "max_score": q.max_score or 1.0,
                    }
                )
                sa_answers[q.id] = {
                    "answer_value": ans.answer_value,
                    "answer_id": ans.id,
                }

        # Commit any autobegin transaction from the reads, then close session
        await db_a.commit()

    return GradingInput(
        attempt_id=attempt_id,
        assessment_id=assessment_id,
        task_id=task_id,
        sa_questions=sa_questions,
        sa_answers=sa_answers,
    )


async def _phase_b_save_and_finalize(
    task_id: str,
    attempt_id: str,
    grades: dict[str, dict[str, Any]],
    grading_source: str,
    grading_status: str,
    sa_questions: list[dict[str, Any]],
    sa_answers: dict[str, dict[str, Any]],
) -> None:
    """Session B: FOR UPDATE attempt, save scores, finalize, commit, close."""
    factory = get_session_factory()
    async with factory() as db_b:
        # FOR UPDATE re-acquire
        attempt_result_b = await db_b.execute(
            select(AssessmentAttempt).where(AssessmentAttempt.id == attempt_id).with_for_update()
        )
        attempt_b = attempt_result_b.scalar_one_or_none()
        if not attempt_b:
            raise ValueError(f"Attempt {attempt_id} not found on re-acquire")

        # Load answer rows for update
        for q in sa_questions:
            q_id = q["id"]
            grade = grades.get(q_id, {"score": 0, "feedback": ""})
            answer_info = sa_answers.get(q_id)
            if not answer_info:
                continue

            ans_result = await db_b.execute(
                select(AssessmentAnswer)
                .where(
                    AssessmentAnswer.attempt_id == attempt_id,
                    AssessmentAnswer.question_id == q_id,
                )
                .with_for_update()
            )
            ans = ans_result.scalar_one_or_none()
            if not ans:
                continue

            max_d = _d(q["max_score"])
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

        # Finalize
        attempt_b.status = "completed"
        attempt_b.grading_quality = "final" if grading_status == "graded" else "provisional"
        attempt_b.active_task_id = None
        attempt_b.submitted_at = attempt_b.submitted_at or datetime.now(UTC)

        await _aggregate_attempt_score(db_b, attempt_b)

        from app.services.assessment_finalization import finalize_assessment_attempt

        await finalize_assessment_attempt(db_b, attempt_id=attempt_id)
        await db_b.commit()


async def _finalize_no_sa(task_id: str, attempt_id: str) -> None:
    """Finalize an attempt that has no short-answer questions (or no answers)."""
    factory = get_session_factory()
    async with factory() as db:
        attempt_result = await db.execute(
            select(AssessmentAttempt).where(AssessmentAttempt.id == attempt_id).with_for_update()
        )
        attempt = attempt_result.scalar_one_or_none()
        if not attempt:
            raise ValueError(f"Attempt {attempt_id} not found")

        attempt.status = "completed"
        attempt.grading_quality = "final"
        attempt.active_task_id = None
        attempt.submitted_at = attempt.submitted_at or datetime.now(UTC)

        await _aggregate_attempt_score(db, attempt)

        from app.services.assessment_finalization import finalize_assessment_attempt

        await finalize_assessment_attempt(db, attempt_id=attempt_id)
        await db.commit()


async def _aggregate_attempt_score(db: Any, attempt: AssessmentAttempt) -> None:
    """Calculate aggregate score for an attempt."""
    from sqlalchemy import func as sa_func

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
