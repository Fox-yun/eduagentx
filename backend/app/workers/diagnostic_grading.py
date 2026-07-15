"""Diagnostic grading worker — scores short-answer questions via LLM,
aggregates results, and transitions the goal to planning with a path generation task.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select

from app.models.diagnostic import DiagnosticAnswer, DiagnosticAttempt, DiagnosticResult
from app.models.goal import LearningGoal
from app.services.diagnostic_scoring import (
    aggregate_results,
    score_short_answer,
)
from app.services.goal import GoalService
from app.services.llm import LLMError, llm_json
from app.workers.task_handlers import register_handler

logger = structlog.get_logger()


DIAGNOSTIC_GRADING_TIMEOUT = 30  # seconds per short-answer question


@register_handler("diagnostic_grading")
async def execute_diagnostic_grading(db: Any, task: Any) -> dict[str, Any]:
    """Grade a diagnostic attempt's short-answer questions via LLM.

    Two-phase approach:
      1. Phase A (DB): load attempt, questions, and existing answers.
         Update task progress.
      2. Phase A.N (no DB): call LLM for each ungraded short-answer question.
      3. Phase B (DB): save scores, aggregate result, transition attempt→completed,
         goal→planning, create path generation task + outbox.

    Phase B is a single transaction. If it fails, the attempt stays in 'grading'
    and the task can be retried.
    """
    from app.models.task import BackgroundTask
    from app.workers.task_runtime import update_task_status

    # -------------------------------------------------------------------
    # Phase A — load data (transaction)
    # -------------------------------------------------------------------

    # Load task
    result_query = await db.execute(select(BackgroundTask).where(BackgroundTask.id == task.id))
    db_task = result_query.scalar_one_or_none()
    if not db_task:
        return {"status": "error", "message": "Task not found"}

    attempt_id = db_task.target_id
    if not attempt_id:
        return {"status": "error", "message": "Task has no target_id"}

    await update_task_status(db, task.id, "running", progress=10, stage="loading", message="正在加载诊断数据...")

    # Load attempt
    attempt_result = await db.execute(
        select(DiagnosticAttempt).where(DiagnosticAttempt.id == attempt_id).with_for_update()
    )
    attempt = attempt_result.scalar_one_or_none()
    if not attempt:
        return {"status": "error", "message": f"Attempt {attempt_id} not found"}

    # Idempotency: if already completed, return existing result
    if attempt.status == "completed":
        existing_result = await db.execute(select(DiagnosticResult).where(DiagnosticResult.attempt_id == attempt_id))
        result_row = existing_result.scalar_one_or_none()
        return {
            "status": "completed",
            "attempt_id": attempt_id,
            "result_id": result_row.id if result_row else None,
        }

    if attempt.status != "grading":
        return {"status": "error", "message": f"Attempt is {attempt.status}, expected grading"}

    # Load the goal
    goal_result = await db.execute(select(LearningGoal).where(LearningGoal.id == attempt.goal_id))
    goal = goal_result.scalar_one_or_none()
    if not goal:
        return {"status": "error", "message": f"Goal {attempt.goal_id} not found"}

    # Read cached questions from DB (generated once during GET endpoint)
    from app.routers.diagnostics import _load_stored_questions

    await update_task_status(db, task.id, "running", progress=20, stage="loading", message="正在加载诊断题目...")

    questions = await _load_stored_questions(db, attempt.goal_id)
    if not questions:
        # Fallback: generate if not in DB (shouldn't happen normally)
        from app.routers.diagnostics import _generate_diagnostic_questions_llm, _store_questions

        await update_task_status(db, task.id, "running", progress=25, stage="generating", message="正在生成诊断题目...")

        profile_context = None
        try:
            from app.services.profile_context import load_learner_profile_context

            profile_context = await load_learner_profile_context(db, user_id=attempt.user_id)
        except Exception:
            logger.debug("profile_context_load_failed", exc_info=True)

        questions = await _generate_diagnostic_questions_llm(goal, profile_context)
        questions = await _store_questions(db, attempt.goal_id, questions)
        await db.commit()

    q_map: dict[str, dict[str, Any]] = {q["question_id"]: q for q in questions}

    # Load existing answers
    answers_result = await db.execute(select(DiagnosticAnswer).where(DiagnosticAnswer.attempt_id == attempt_id))
    db_answers: list[DiagnosticAnswer] = list(answers_result.scalars().all())

    await db.flush()

    # -------------------------------------------------------------------
    # Phase A.N — call LLM for short-answer questions (NO transaction)
    # -------------------------------------------------------------------
    await update_task_status(db, task.id, "running", progress=40, stage="grading", message="智能体正在评分简答题...")
    llm_results: dict[str, dict[str, Any] | None] = {}

    for answer_record in db_answers:
        q = q_map.get(answer_record.question_id)
        if not q:
            continue

        # Only grade short_answer questions that haven't been program-scored
        if q.get("type") != "short_answer":
            continue
        if answer_record.grading_source == "program":
            continue  # already scored by program

        rubric = q.get("rubric", "")
        prompt = q.get("prompt", "")
        user_answer = answer_record.answer or ""
        max_score_val = float(q.get("max_score", 10))

        system_prompt = (
            "你是一个专业的教育评估智能体。你的任务是根据评分标准对学生简答题的回答进行评分。\n\n"
            "请返回严格的 JSON 格式，包含以下字段：\n"
            "- score: 0 到最大分数之间的数值\n"
            "- feedback: 简短的评语（中文）\n"
            "- matched_criteria: 学生达到的评分标准列表\n"
            "- missing_criteria: 学生未达到的评分标准列表\n"
            "不要返回其他字段。"
        )

        user_msg = (
            f"题目：{prompt}\n\n"
            f"评分标准（Rubric）：{rubric}\n\n"
            f"最大分数：{max_score_val}\n\n"
            f"学生回答：{user_answer}\n\n"
            f"请根据评分标准给出 0 到 {max_score_val} 之间的评分。"
        )

        try:
            structured_result = await llm_json(
                system_prompt,
                user_msg,
                temperature=0.3,
                max_tokens=1024,
            )
            llm_results[answer_record.question_id] = structured_result
            logger.info(
                "diagnostic_short_answer_graded",
                attempt_id=attempt_id,
                question_id=answer_record.question_id,
            )
        except (LLMError, TimeoutError, ValueError) as e:
            logger.warning(
                "diagnostic_short_answer_llm_failed",
                attempt_id=attempt_id,
                question_id=answer_record.question_id,
                error=str(e)[:200],
            )
            # LLM failed — will be scored as provisional in Phase B
            llm_results[answer_record.question_id] = None

    # -------------------------------------------------------------------
    # Phase B — save results, transition states (single transaction)
    # -------------------------------------------------------------------
    await update_task_status(db, task.id, "running", progress=70, stage="aggregating", message="正在汇总评分结果...")
    return await _finalize_grading_transaction(
        db=db,
        attempt=attempt,
        goal=goal,
        attempt_id=attempt_id,
        db_answers=db_answers,
        q_map=q_map,
        llm_results=llm_results,
    )


async def _finalize_grading_transaction(
    *,
    db: Any,
    attempt: DiagnosticAttempt,
    goal: LearningGoal,
    attempt_id: str,
    db_answers: list[DiagnosticAnswer],
    q_map: dict[str, dict[str, Any]],
    llm_results: dict[str, dict[str, Any] | None],
) -> dict[str, Any]:
    """Persist grading, goal transition, and path task atomically."""
    try:
        now_utc = datetime.now(UTC)

        for answer_record in db_answers:
            q = q_map.get(answer_record.question_id, {})
            q_type = q.get("type", "")
            max_score = Decimal(str(q.get("max_score", 10)))

            if q_type == "short_answer":
                llm_result = llm_results.get(answer_record.question_id)
                sa = score_short_answer(answer_record.answer or "", llm_result, max_score)
                answer_record.score = float(sa.score)
                answer_record.is_correct = sa.is_correct
                answer_record.feedback = sa.feedback
                answer_record.grading_source = sa.grading_source
                answer_record.grading_status = sa.grading_status
                answer_record.updated_at = now_utc

        all_answers_result = await db.execute(
            select(DiagnosticAnswer).where(DiagnosticAnswer.attempt_id == attempt_id)
        )
        all_answers = list(all_answers_result.scalars().all())

        from app.services.diagnostic_scoring import ScoredAnswer

        scored_answers = [
            ScoredAnswer(
                question_id=a.question_id,
                score=Decimal(str(a.score)),
                max_score=Decimal(str(a.max_score)),
                is_correct=a.is_correct,
                feedback=a.feedback,
                grading_source=a.grading_source or "program",
                grading_status=a.grading_status or "graded",
            )
            for a in all_answers
        ]
        question_dicts = [
            {
                "id": a.question_id,
                "dimension": q_map.get(a.question_id, {}).get("dimension", "general"),
                "max_score": a.max_score,
            }
            for a in all_answers
        ]
        aggregated = aggregate_results(scored_answers, question_dicts)

        any_provisional = any(
            a.grading_status == "provisional" or a.grading_source == "fallback" for a in all_answers
        )
        grading_quality = "provisional" if any_provisional else "final"
        strong_areas = [dim for dim, pct in aggregated.dimension_scores.items() if pct >= 60.0]
        weak_areas = [dim for dim, pct in aggregated.dimension_scores.items() if pct < 60.0]

        diag_result = DiagnosticResult(
            id=str(uuid.uuid4()),
            attempt_id=attempt_id,
            total_score=float(aggregated.total_score),
            percentage=aggregated.percentage,
            dimension_scores=aggregated.dimension_scores,
            strong_areas=strong_areas,
            weak_areas=weak_areas,
            readiness_level=aggregated.readiness_level,
            grading_quality=grading_quality,
        )
        db.add(diag_result)

        attempt.status = "completed"
        attempt.completed_at = now_utc
        attempt.grading_quality = grading_quality
        attempt.updated_at = now_utc

        goal_service = GoalService(db)
        await goal_service.transition_goal(goal.id, goal.user_id, "planning", commit=False)

        from app.services.task import TaskService

        task_service = TaskService(db)
        path_task = await task_service.enqueue_task(
            user_id=goal.user_id,
            task_type="learning_path_generation",
            target_type="goal",
            target_id=goal.id,
            idempotency_key=f"path-generate:{goal.id}",
        )
        goal.active_task_id = path_task.id

        try:
            from app.services.profile_merge import apply_diagnostic_evidence

            async with db.begin_nested():
                await apply_diagnostic_evidence(
                    db,
                    user_id=goal.user_id,
                    attempt_id=attempt_id,
                    percentage=aggregated.percentage,
                    weak_areas=weak_areas,
                )
        except Exception as e:
            logger.warning(
                "profile_merge_diagnostic_failed",
                error=str(e),
                attempt_id=attempt_id,
            )

        await db.flush()
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    logger.info(
        "diagnostic_grading_completed",
        attempt_id=attempt_id,
        result_id=diag_result.id,
        grading_quality=grading_quality,
        percentage=aggregated.percentage,
        path_task_id=path_task.id,
    )
    return {
        "status": "completed",
        "attempt_id": attempt_id,
        "result_id": diag_result.id,
        "grading_quality": grading_quality,
        "percentage": aggregated.percentage,
        "readiness_level": aggregated.readiness_level,
        "path_task_id": path_task.id,
    }
