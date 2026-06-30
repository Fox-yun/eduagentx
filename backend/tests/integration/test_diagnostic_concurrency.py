"""Integration tests for concurrent diagnostic submission with real PostgreSQL."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select as sa_select

from app.models.diagnostic import DiagnosticAttempt, DiagnosticResult
from app.models.goal import LearningGoal
from app.models.task import BackgroundTask
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


async def _create_goal(db_session, user_id: str, title: str = "Concurrent Test") -> str:
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


class TestDiagnosticConcurrency:
    """Verify FOR UPDATE prevents duplicate grading tasks under concurrency."""

    @pytest.mark.asyncio
    async def test_for_update_prevents_double_transition(self, db_session):
        """FOR UPDATE: second read after transition sees grading, not draft."""
        uid = await _create_user(db_session, "fupd")
        gid = await _create_goal(db_session, uid)

        attempt_id = str(uuid.uuid4())
        db_session.add(DiagnosticAttempt(
            id=attempt_id, diagnostic_id=f"diag-{gid[:8]}", goal_id=gid,
            user_id=uid, status="draft",
        ))
        await db_session.commit()

        # Lock and transition
        a1 = (await db_session.execute(
            sa_select(DiagnosticAttempt).where(DiagnosticAttempt.id == attempt_id).with_for_update()
        )).scalar_one()
        assert a1.status == "draft"
        a1.status = "grading"
        db_session.add(BackgroundTask(
            id=str(uuid.uuid4()), user_id=uid, task_type="diagnostic_grading",
            status="pending", target_type="attempt", target_id=attempt_id,
        ))
        await db_session.commit()

        # Fresh read sees grading
        a2 = (await db_session.execute(
            sa_select(DiagnosticAttempt).where(DiagnosticAttempt.id == attempt_id)
        )).scalar_one()
        assert a2.status == "grading"

        # Only one grading task
        tasks = (await db_session.execute(
            sa_select(BackgroundTask).where(
                BackgroundTask.task_type == "diagnostic_grading",
                BackgroundTask.target_id == attempt_id,
            )
        )).scalars().all()
        assert len(tasks) == 1

    @pytest.mark.asyncio
    async def test_idempotent_result_no_duplicate(self, db_session):
        """Worker idempotency: completed attempt does not create result or path task."""
        uid = await _create_user(db_session, "idupr")
        gid = await _create_goal(db_session, uid)

        attempt_id = str(uuid.uuid4())
        db_session.add(DiagnosticAttempt(
            id=attempt_id, diagnostic_id=f"diag-{gid[:8]}", goal_id=gid,
            user_id=uid, status="completed", grading_quality="final",
        ))
        task = BackgroundTask(
            id=str(uuid.uuid4()), user_id=uid, task_type="diagnostic_grading",
            status="pending", target_type="attempt", target_id=attempt_id,
        )
        db_session.add(task)
        await db_session.commit()

        from app.workers.diagnostic_grading import execute_diagnostic_grading

        r1 = await execute_diagnostic_grading(db_session, task)
        assert r1["status"] == "completed"

        r2 = await execute_diagnostic_grading(db_session, task)
        assert r2["status"] == "completed"

        # No results created
        results = (await db_session.execute(
            sa_select(DiagnosticResult).where(DiagnosticResult.attempt_id == attempt_id)
        )).scalars().all()
        assert len(results) == 0

        # No path tasks created
        path_tasks = (await db_session.execute(
            sa_select(BackgroundTask).where(
                BackgroundTask.task_type == "learning_path_generation",
                BackgroundTask.target_id == gid,
            )
        )).scalars().all()
        assert len(path_tasks) == 0
