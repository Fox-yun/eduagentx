"""Integration tests for diagnostic → planning transition with real PostgreSQL."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select as sa_select

from app.models.diagnostic import DiagnosticAnswer, DiagnosticAttempt, DiagnosticResult
from app.models.goal import LearningGoal
from app.models.outbox import OutboxEvent
from app.models.task import BackgroundTask, TaskEvent
from app.models.user import User


async def _create_user(db_session, prefix: str) -> str:
    uid = str(uuid.uuid4())
    user = User(
        id=uid,
        email=f"{prefix}-{uid[:8]}@t.example.com",
        email_normalized=f"{prefix}-{uid[:8]}@t.example.com",
        display_name=prefix,
        password_hash="hash",
        status="active",
        email_verified_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.commit()
    return uid


async def _create_goal(db_session, user_id: str) -> str:
    gid = str(uuid.uuid4())
    goal = LearningGoal(
        id=gid,
        user_id=user_id,
        title="Learn Python",
        raw_description="Learn Python",
        status="diagnosing",
    )
    db_session.add(goal)
    await db_session.commit()
    return gid


async def _setup_grading_attempt(
    db_session, user_id: str, goal_id: str
) -> tuple[str, str, list[dict]]:
    """Create an attempt that looks like it's ready for grading completion."""
    attempt_id = str(uuid.uuid4())
    attempt = DiagnosticAttempt(
        id=attempt_id,
        diagnostic_id=f"diag-{goal_id[:8]}",
        goal_id=goal_id,
        user_id=user_id,
        status="grading",
    )
    db_session.add(attempt)

    task_id = str(uuid.uuid4())
    task = BackgroundTask(
        id=task_id,
        user_id=user_id,
        task_type="diagnostic_grading",
        status="running",
        target_type="attempt",
        target_id=attempt_id,
    )
    db_session.add(task)

    # Create objective answers already scored
    goal = (await db_session.execute(sa_select(LearningGoal).where(LearningGoal.id == goal_id))).scalar_one()
    from app.routers.diagnostics import _generate_diagnostic_questions

    questions = _generate_diagnostic_questions(goal)
    for q in questions:
        if q.get("type") == "short_answer":
            correct = q.get("correct_answer")
            ans = DiagnosticAnswer(
                id=str(uuid.uuid4()),
                attempt_id=attempt_id,
                question_id=q["question_id"],
                answer="My answer",
                score=float(q.get("max_score", 10)) * 0.5,
                max_score=float(q.get("max_score", 10)),
                is_correct=None,
                grading_source="fallback",
                grading_status="provisional",
            )
            db_session.add(ans)
            continue
        correct = q.get("correct_answer")
        if correct is None:
            continue
        ans = DiagnosticAnswer(
            id=str(uuid.uuid4()),
            attempt_id=attempt_id,
            question_id=q["question_id"],
            answer=str(correct[0]) if isinstance(correct, list) else str(correct),
            score=float(q.get("max_score", 10)),
            max_score=float(q.get("max_score", 10)),
            is_correct=True,
            grading_source="program",
            grading_status="graded",
        )
        db_session.add(ans)

    await db_session.commit()
    return attempt_id, task_id, questions


class TestDiagnosticPlanningTransition:
    """Integration tests for the grading completion → planning transition."""

    @pytest.mark.asyncio
    async def test_worker_completes_attempt_and_transitions_goal(self, db_session):
        """After grading: attempt=completed, result=created, goal=planning."""
        from app.workers.diagnostic_grading import execute_diagnostic_grading

        uid = await _create_user(db_session, "plan")
        gid = await _create_goal(db_session, uid)
        attempt_id, task_id, _ = await _setup_grading_attempt(db_session, uid, gid)

        with patch("app.workers.diagnostic_grading.llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {"score": 7.0, "feedback": "Good"}
            task = (
                await db_session.execute(sa_select(BackgroundTask).where(BackgroundTask.id == task_id))
            ).scalar_one()
            result = await execute_diagnostic_grading(db_session, task)

        assert result["status"] == "completed"

        # Attempt → completed
        attempt = (
            await db_session.execute(sa_select(DiagnosticAttempt).where(DiagnosticAttempt.id == attempt_id))
        ).scalar_one()
        assert attempt.status == "completed"

        # Result → created
        diag_result = (
            await db_session.execute(sa_select(DiagnosticResult).where(DiagnosticResult.attempt_id == attempt_id))
        ).scalar_one()
        assert diag_result.id is not None
        assert diag_result.percentage > 0

        # Goal → planning
        goal = (await db_session.execute(sa_select(LearningGoal).where(LearningGoal.id == gid))).scalar_one()
        assert goal.status == "planning"

        # Path task → created
        path_tasks = (
            (
                await db_session.execute(
                    sa_select(BackgroundTask).where(
                        BackgroundTask.task_type == "learning_path_generation",
                        BackgroundTask.target_id == gid,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(path_tasks) == 1

    @pytest.mark.asyncio
    async def test_goal_does_not_transition_on_error(self, db_session):
        """If grading fails, goal stays at diagnosing."""
        from app.workers.diagnostic_grading import execute_diagnostic_grading

        uid = await _create_user(db_session, "fail")
        gid = await _create_goal(db_session, uid)
        attempt_id, task_id, _ = await _setup_grading_attempt(db_session, uid, gid)

        # Force an error by making the attempt non-existent
        bad_task = (
            await db_session.execute(sa_select(BackgroundTask).where(BackgroundTask.id == task_id))
        ).scalar_one()
        bad_task.target_id = "no-such-attempt"
        await db_session.commit()

        result = await execute_diagnostic_grading(db_session, bad_task)
        assert result["status"] == "error"

        # Goal unchanged
        goal = (await db_session.execute(sa_select(LearningGoal).where(LearningGoal.id == gid))).scalar_one()
        assert goal.status == "diagnosing"

    @pytest.mark.asyncio
    async def test_provisional_grading_quality(self, db_session):
        """LLM failure produces provisional grading with fallback."""
        from app.workers.diagnostic_grading import execute_diagnostic_grading
        from app.services.llm import LLMError

        uid = await _create_user(db_session, "prov")
        gid = await _create_goal(db_session, uid)
        attempt_id, task_id, _ = await _setup_grading_attempt(db_session, uid, gid)

        with patch("app.workers.diagnostic_grading.llm_json", new_callable=AsyncMock, side_effect=LLMError("Down")):
            task = (
                await db_session.execute(sa_select(BackgroundTask).where(BackgroundTask.id == task_id))
            ).scalar_one()
            result = await execute_diagnostic_grading(db_session, task)

        assert result["status"] == "completed"
        assert result["grading_quality"] == "provisional"

        attempt = (
            await db_session.execute(sa_select(DiagnosticAttempt).where(DiagnosticAttempt.id == attempt_id))
        ).scalar_one()
        assert attempt.grading_quality == "provisional"

        diag_result = (
            await db_session.execute(sa_select(DiagnosticResult).where(DiagnosticResult.attempt_id == attempt_id))
        ).scalar_one()
        assert diag_result.grading_quality == "provisional"

        # Goal still transitions
        goal = (await db_session.execute(sa_select(LearningGoal).where(LearningGoal.id == gid))).scalar_one()
        assert goal.status == "planning"

    @pytest.mark.asyncio
    async def test_path_task_has_idempotency_key(self, db_session):
        """Path task is created with idempotency key to prevent duplicates."""
        from app.workers.diagnostic_grading import execute_diagnostic_grading

        uid = await _create_user(db_session, "idem2")
        gid = await _create_goal(db_session, uid)
        attempt_id, task_id, _ = await _setup_grading_attempt(db_session, uid, gid)

        with patch("app.workers.diagnostic_grading.llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {"score": 8.0, "feedback": "Good work"}
            task = (
                await db_session.execute(sa_select(BackgroundTask).where(BackgroundTask.id == task_id))
            ).scalar_one()
            await execute_diagnostic_grading(db_session, task)

        # Re-run should be idempotent (already completed)
        task2 = (
            await db_session.execute(sa_select(BackgroundTask).where(BackgroundTask.id == task_id))
        ).scalar_one()
        result2 = await execute_diagnostic_grading(db_session, task2)
        assert result2["status"] == "completed"

        # Only one path task
        path_tasks = (
            (
                await db_session.execute(
                    sa_select(BackgroundTask).where(
                        BackgroundTask.task_type == "learning_path_generation",
                        BackgroundTask.target_id == gid,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(path_tasks) == 1

        # Only one result
        results = (
            (
                await db_session.execute(
                    sa_select(DiagnosticResult).where(DiagnosticResult.attempt_id == attempt_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_answer_and_result_consistency(self, db_session):
        """All answers are scored and result reflects correct aggregation."""
        from app.workers.diagnostic_grading import execute_diagnostic_grading

        uid = await _create_user(db_session, "cons")
        gid = await _create_goal(db_session, uid)
        attempt_id, task_id, _ = await _setup_grading_attempt(db_session, uid, gid)

        with patch("app.workers.diagnostic_grading.llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {"score": 6.0, "feedback": "Adequate"}
            task = (
                await db_session.execute(sa_select(BackgroundTask).where(BackgroundTask.id == task_id))
            ).scalar_one()
            await execute_diagnostic_grading(db_session, task)

        # All answers have scores
        answers = (
            (
                await db_session.execute(
                    sa_select(DiagnosticAnswer).where(DiagnosticAnswer.attempt_id == attempt_id)
                )
            )
            .scalars()
            .all()
        )
        assert all(a.score is not None for a in answers)
        assert all(a.grading_source is not None for a in answers)
        assert all(a.grading_status is not None for a in answers)

        # Result reflects actual data
        result = (
            await db_session.execute(sa_select(DiagnosticResult).where(DiagnosticResult.attempt_id == attempt_id))
        ).scalar_one()
        assert result.total_score > 0
        assert result.percentage > 0
        assert result.readiness_level is not None
        assert result.dimension_scores is not None
