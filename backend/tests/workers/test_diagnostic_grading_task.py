"""Worker tests for diagnostic grading task."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select as sa_select

from app.models.diagnostic import DiagnosticAnswer, DiagnosticAttempt
from app.models.goal import LearningGoal
from app.models.task import BackgroundTask
from app.models.user import User
from app.services.llm import LLMError


async def _create_user(db_session, prefix: str) -> str:
    """Helper to create a unique user."""
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


async def _create_goal(db_session, user_id: str, title: str) -> str:
    """Helper to create a learning goal."""
    gid = str(uuid.uuid4())
    goal = LearningGoal(
        id=gid,
        user_id=user_id,
        title=title,
        raw_description=title,
        status="diagnosing",
    )
    db_session.add(goal)
    await db_session.commit()
    return gid


async def _reload_task(db_session, task_id: str):
    result = await db_session.execute(sa_select(BackgroundTask).where(BackgroundTask.id == task_id))
    return result.scalar_one()


class TestDiagnosticGradingWorker:
    @pytest.mark.asyncio
    async def test_all_objective_no_llm(self, db_session):
        """Grading with only objective questions completes without LLM call."""
        from app.workers.diagnostic_grading import execute_diagnostic_grading

        uid = await _create_user(db_session, "obj")
        gid = await _create_goal(db_session, uid, "Learn Python programming")

        attempt_id = str(uuid.uuid4())
        attempt = DiagnosticAttempt(
            id=attempt_id,
            diagnostic_id=f"diag-{gid[:8]}",
            goal_id=gid,
            user_id=uid,
            status="grading",
        )
        db_session.add(attempt)

        task = BackgroundTask(
            id=str(uuid.uuid4()),
            user_id=uid,
            task_type="diagnostic_grading",
            status="pending",
            target_type="attempt",
            target_id=attempt_id,
        )
        db_session.add(task)
        await db_session.commit()

        # Re-generate questions from bank and add scored answers
        goal = (await db_session.execute(sa_select(LearningGoal).where(LearningGoal.id == gid))).scalar_one()
        from app.routers.diagnostics import _generate_diagnostic_questions

        questions = _generate_diagnostic_questions(goal)
        for q in questions:
            if q.get("type") == "short_answer":
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

        t = await _reload_task(db_session, task.id)
        result = await execute_diagnostic_grading(db_session, t)

        assert result["status"] == "completed"
        assert result["percentage"] >= 0

        # Verify attempt → completed
        attempt_after = (
            await db_session.execute(sa_select(DiagnosticAttempt).where(DiagnosticAttempt.id == attempt_id))
        ).scalar_one()
        assert attempt_after.status == "completed"

        # Verify goal → planning
        goal_after = (await db_session.execute(sa_select(LearningGoal).where(LearningGoal.id == gid))).scalar_one()
        assert goal_after.status == "planning"

    @pytest.mark.asyncio
    async def test_short_answer_llm_fallback(self, db_session):
        """LLM failure produces provisional grading_quality."""
        from app.workers.diagnostic_grading import execute_diagnostic_grading

        uid = await _create_user(db_session, "fal")
        gid = await _create_goal(db_session, uid, "Learn Python programming")

        attempt_id = str(uuid.uuid4())
        attempt = DiagnosticAttempt(
            id=attempt_id,
            diagnostic_id=f"diag-{gid[:8]}",
            goal_id=gid,
            user_id=uid,
            status="grading",
        )
        db_session.add(attempt)

        task = BackgroundTask(
            id=str(uuid.uuid4()),
            user_id=uid,
            task_type="diagnostic_grading",
            status="pending",
            target_type="attempt",
            target_id=attempt_id,
        )
        db_session.add(task)
        await db_session.commit()

        goal = (await db_session.execute(sa_select(LearningGoal).where(LearningGoal.id == gid))).scalar_one()
        from app.routers.diagnostics import _generate_diagnostic_questions

        questions = _generate_diagnostic_questions(goal)

        # Add scored objective + an ungraded short_answer
        sa_q = None
        for q in questions:
            if q.get("type") == "short_answer" and sa_q is None:
                sa_q = q
                sa_ans = DiagnosticAnswer(
                    id=str(uuid.uuid4()),
                    attempt_id=attempt_id,
                    question_id=q["question_id"],
                    answer="My answer text",
                    score=0.0,
                    max_score=float(q.get("max_score", 10)),
                    is_correct=None,
                    grading_source="llm",
                    grading_status="provisional",
                )
                db_session.add(sa_ans)
            elif q.get("correct_answer") is not None and q.get("type") != "short_answer":
                correct = q["correct_answer"]
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

        with patch("app.workers.diagnostic_grading.llm_json", new_callable=AsyncMock, side_effect=LLMError("LLM down")):
            t = await _reload_task(db_session, task.id)
            result = await execute_diagnostic_grading(db_session, t)

        assert result["status"] == "completed"
        assert result["grading_quality"] == "provisional"

        attempt_after = (
            await db_session.execute(sa_select(DiagnosticAttempt).where(DiagnosticAttempt.id == attempt_id))
        ).scalar_one()
        assert attempt_after.status == "completed"

        goal_after = (await db_session.execute(sa_select(LearningGoal).where(LearningGoal.id == gid))).scalar_one()
        assert goal_after.status == "planning"

    @pytest.mark.asyncio
    async def test_already_completed_idempotent(self, db_session):
        """Already completed attempt returns success without creating duplicates."""
        from app.workers.diagnostic_grading import execute_diagnostic_grading

        uid = await _create_user(db_session, "idem")
        gid = await _create_goal(db_session, uid, "Learn Python")

        attempt_id = str(uuid.uuid4())
        attempt = DiagnosticAttempt(
            id=attempt_id,
            diagnostic_id=f"diag-{gid[:8]}",
            goal_id=gid,
            user_id=uid,
            status="completed",
            grading_quality="final",
        )
        db_session.add(attempt)

        task = BackgroundTask(
            id=str(uuid.uuid4()),
            user_id=uid,
            task_type="diagnostic_grading",
            status="pending",
            target_type="attempt",
            target_id=attempt_id,
        )
        db_session.add(task)
        await db_session.commit()

        t = await _reload_task(db_session, task.id)
        result = await execute_diagnostic_grading(db_session, t)

        assert result["status"] == "completed"

        # No duplicate path tasks for THIS goal
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
        assert len(path_tasks) == 0

    @pytest.mark.asyncio
    async def test_attempt_not_found(self, db_session):
        """Non-existent attempt returns error."""
        from app.workers.diagnostic_grading import execute_diagnostic_grading

        uid = await _create_user(db_session, "nf")
        bad_task = BackgroundTask(
            id=str(uuid.uuid4()),
            user_id=uid,
            task_type="diagnostic_grading",
            status="pending",
            target_type="attempt",
            target_id="no-such-attempt",
        )
        db_session.add(bad_task)
        await db_session.commit()

        result = await execute_diagnostic_grading(db_session, bad_task)
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_no_target_id(self, db_session):
        """Task without target_id returns error."""
        from app.workers.diagnostic_grading import execute_diagnostic_grading

        uid = await _create_user(db_session, "nt")
        bad_task = BackgroundTask(
            id=str(uuid.uuid4()),
            user_id=uid,
            task_type="diagnostic_grading",
            status="pending",
            target_type="attempt",
            target_id=None,
        )
        db_session.add(bad_task)
        await db_session.commit()

        result = await execute_diagnostic_grading(db_session, bad_task)
        assert result["status"] == "error"
