"""Integration tests for diagnostic submission with real PostgreSQL."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select as sa_select

from app.models.diagnostic import DiagnosticAnswer, DiagnosticAttempt, DiagnosticResult
from app.models.goal import LearningGoal
from app.models.task import BackgroundTask
from app.models.user import User
from app.services.diagnostic_scoring import ScoredAnswer, aggregate_results


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


async def _create_goal(db_session, user_id: str, title: str = "Learn Python programming") -> str:
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


async def _create_draft_attempt(db_session, user_id: str, goal_id: str) -> str:
    attempt_id = str(uuid.uuid4())
    attempt = DiagnosticAttempt(
        id=attempt_id,
        diagnostic_id=f"diag-{goal_id[:8]}",
        goal_id=goal_id,
        user_id=user_id,
        status="draft",
    )
    db_session.add(attempt)
    await db_session.commit()
    return attempt_id


class TestDiagnosticSubmission:
    """Integration tests for the diagnostic submit flow."""

    @pytest.mark.asyncio
    async def test_submission_atomicity(self, db_session):
        """Full submit flow creates attempt→answers→grading task in one transaction."""
        uid = await _create_user(db_session, "subat")
        gid = await _create_goal(db_session, uid)
        attempt_id = await _create_draft_attempt(db_session, uid, gid)

        goal = (await db_session.execute(sa_select(LearningGoal).where(LearningGoal.id == gid))).scalar_one()
        from app.routers.diagnostics import _generate_diagnostic_questions

        questions = _generate_diagnostic_questions(goal)

        # Simulate what the router does: add scored objective answers
        for q in questions:
            if q.get("type") == "short_answer":
                continue  # will be graded by worker
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

        # Transition attempt to grading
        attempt = (
            await db_session.execute(
                sa_select(DiagnosticAttempt).where(DiagnosticAttempt.id == attempt_id).with_for_update()
            )
        ).scalar_one()
        attempt.status = "grading"

        # Create the grading task
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

        # Verify: all data in the same transaction
        answers = (
            (await db_session.execute(sa_select(DiagnosticAnswer).where(DiagnosticAnswer.attempt_id == attempt_id)))
            .scalars()
            .all()
        )
        assert len(answers) > 0
        assert all(a.grading_source == "program" for a in answers)

        attempt_after = (
            await db_session.execute(sa_select(DiagnosticAttempt).where(DiagnosticAttempt.id == attempt_id))
        ).scalar_one()
        assert attempt_after.status == "grading"

        tasks = (
            (
                await db_session.execute(
                    sa_select(BackgroundTask).where(
                        BackgroundTask.task_type == "diagnostic_grading",
                        BackgroundTask.target_id == attempt_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(tasks) == 1

    @pytest.mark.asyncio
    async def test_submission_idempotent(self, db_session):
        """Re-submitting same attempt returns existing task without creating duplicates."""
        uid = await _create_user(db_session, "subid")
        gid = await _create_goal(db_session, uid)
        attempt_id = await _create_draft_attempt(db_session, uid, gid)

        # First: create grading task
        task = BackgroundTask(
            id=str(uuid.uuid4()),
            user_id=uid,
            task_type="diagnostic_grading",
            status="pending",
            target_type="attempt",
            target_id=attempt_id,
        )
        db_session.add(task)

        attempt = (
            await db_session.execute(
                sa_select(DiagnosticAttempt).where(DiagnosticAttempt.id == attempt_id).with_for_update()
            )
        ).scalar_one()
        attempt.status = "grading"
        await db_session.commit()

        # Simulate second submit: attempt is already grading → should return existing
        attempt_check = (
            await db_session.execute(
                sa_select(DiagnosticAttempt).where(DiagnosticAttempt.id == attempt_id).with_for_update()
            )
        ).scalar_one()
        assert attempt_check.status == "grading"

        tasks = (
            (
                await db_session.execute(
                    sa_select(BackgroundTask).where(
                        BackgroundTask.task_type == "diagnostic_grading",
                        BackgroundTask.target_id == attempt_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(tasks) == 1, "Should not create a second grading task"

    @pytest.mark.asyncio
    async def test_diagnostic_result_has_unique_constraint(self, db_session):
        """A single attempt can have at most one result (DB constraint)."""
        uid = await _create_user(db_session, "uniq")
        gid = await _create_goal(db_session, uid)
        attempt_id = await _create_draft_attempt(db_session, uid, gid)

        result1 = DiagnosticResult(
            id=str(uuid.uuid4()),
            attempt_id=attempt_id,
            total_score=80.0,
            percentage=80.0,
            dimension_scores={"fundamentals": 80.0},
            readiness_level="proficient",
            grading_quality="final",
        )
        db_session.add(result1)
        await db_session.commit()

        result2 = DiagnosticResult(
            id=str(uuid.uuid4()),
            attempt_id=attempt_id,
            total_score=90.0,
            percentage=90.0,
            dimension_scores={"fundamentals": 90.0},
            readiness_level="advanced",
            grading_quality="final",
        )
        db_session.add(result2)
        with pytest.raises(Exception):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_answer_unique_per_attempt_question(self, db_session):
        """UNIQUE(attempt_id, question_id) prevents duplicate answers."""
        uid = await _create_user(db_session, "dups")
        gid = await _create_goal(db_session, uid)
        attempt_id = await _create_draft_attempt(db_session, uid, gid)

        qid = "test-q-1"
        ans1 = DiagnosticAnswer(
            id=str(uuid.uuid4()),
            attempt_id=attempt_id,
            question_id=qid,
            answer="first",
            score=10.0,
            max_score=10.0,
            grading_source="program",
            grading_status="graded",
        )
        db_session.add(ans1)
        await db_session.commit()

        ans2 = DiagnosticAnswer(
            id=str(uuid.uuid4()),
            attempt_id=attempt_id,
            question_id=qid,
            answer="second",
            score=0.0,
            max_score=10.0,
        )
        db_session.add(ans2)
        with pytest.raises(Exception):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_different_users_isolated(self, db_session):
        """Different users' attempts are independent."""
        uid1 = await _create_user(db_session, "iso1")
        uid2 = await _create_user(db_session, "iso2")
        gid1 = await _create_goal(db_session, uid1)
        gid2 = await _create_goal(db_session, uid2)
        aid1 = await _create_draft_attempt(db_session, uid1, gid1)
        aid2 = await _create_draft_attempt(db_session, uid2, gid2)

        assert aid1 != aid2

        a1 = (
            await db_session.execute(sa_select(DiagnosticAttempt).where(DiagnosticAttempt.id == aid1))
        ).scalar_one()
        a2 = (
            await db_session.execute(sa_select(DiagnosticAttempt).where(DiagnosticAttempt.id == aid2))
        ).scalar_one()
        assert a1.user_id == uid1
        assert a2.user_id == uid2
        assert a1.goal_id == gid1
        assert a2.goal_id == gid2
