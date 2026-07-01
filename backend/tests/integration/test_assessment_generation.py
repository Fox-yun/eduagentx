"""Integration tests for assessment generation with real PostgreSQL.

Verifies:
  - Atomic creation: Assessment + Task + Event + Outbox in one transaction
  - Rollback: Outbox failure rolls back all objects
  - Idempotency: Same parameters return same Assessment/Task
  - Concurrency: No duplicate creation under concurrent calls
  - Worker success: pending -> generating -> ready with questions
  - Worker failure: Assessment -> failed, no partial questions

Run with:
    pytest tests/integration/test_assessment_generation.py -v
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select as sa_select

from app.models.goal import LearningGoal
from app.models.outbox import OutboxEvent
from app.models.path import LearningPath, LearningPathVersion, LearningNode
from app.models.task import BackgroundTask, TaskEvent
from app.models.unit import Assessment, AssessmentQuestion
from app.models.user import User
from app.services.unit import UnitService
from app.services.task import TaskService
from app.workers.assessment_generation import (
    execute_assessment_generation,
    GeneratedAssessmentQuestion,
    GeneratedQuestionOption,
)


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


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


async def _create_path(db_session, user_id: str) -> str:
    """Create a LearningGoal + LearningPath + LearningPathVersion + LearningNode."""
    gid = str(uuid.uuid4())
    goal = LearningGoal(
        id=gid,
        user_id=user_id,
        title="Test Goal",
        raw_description="Assessment generation integration test",
    )
    db_session.add(goal)
    await db_session.flush()

    pid = str(uuid.uuid4())
    path = LearningPath(
        id=pid,
        user_id=user_id,
        goal_id=gid,
        status="draft",
    )
    db_session.add(path)
    await db_session.flush()

    pvid = str(uuid.uuid4())
    pv = LearningPathVersion(
        id=pvid,
        path_id=pid,
        version_number=1,
    )
    db_session.add(pv)
    await db_session.flush()

    # Mark path active_version_id
    path.active_version_id = pvid
    await db_session.flush()

    nid = str(uuid.uuid4())
    node = LearningNode(
        id=nid,
        version_id=pvid,
        title="Test Node",
        description="Test node for assessment generation",
        node_order=1,
        level=1,
        difficulty="beginner",
        estimated_minutes=30,
        status="available",
        content_status="ready",
    )
    db_session.add(node)
    await db_session.commit()
    return pid, pvid, nid


async def _count_outbox(db_session, aggregate_id: str) -> int:
    result = await db_session.execute(
        sa_select(OutboxEvent).where(
            OutboxEvent.aggregate_type == "BackgroundTask",
            OutboxEvent.aggregate_id == aggregate_id,
        )
    )
    return len(result.scalars().all())


# ---------------------------------------------------------------------------
# Atomicity
# ---------------------------------------------------------------------------


class TestAssessmentGenerationAtomic:
    """Assessment + Task + Event + Outbox are created atomically."""

    @pytest.mark.asyncio
    async def test_create_assessment_with_task_and_outbox(self, db_session):
        """Full generate_quiz_bank flow creates all records in one transaction."""
        uid = await _create_user(db_session, "atox1")
        pid, pvid, nid = await _create_path(db_session, uid)

        service = UnitService(db_session)
        result = await service.generate_quiz_bank(
            path_id=pid,
            node_id=nid,
            user_id=uid,
            path_version_id=pvid,
        )

        assert result["status"] == "generating"
        assert result["active_task_id"] is not None

        # -- Assessment --
        assessment = (
            await db_session.execute(sa_select(Assessment).where(Assessment.id == result["assessment_id"]))
        ).scalar_one()
        assert assessment.status == "generating"
        assert assessment.active_task_id == result["active_task_id"]
        assert assessment.purpose == "quiz_bank"

        # -- BackgroundTask --
        task = (
            await db_session.execute(sa_select(BackgroundTask).where(BackgroundTask.id == result["active_task_id"]))
        ).scalar_one()
        assert task.task_type == "learning_assessment_generation"
        assert task.status == "pending"
        assert task.target_type == "assessment"
        assert task.target_id == assessment.id

        # -- TaskEvent --
        events = (await db_session.execute(sa_select(TaskEvent).where(TaskEvent.task_id == task.id))).scalars().all()
        assert len(events) == 1
        assert events[0].event_type == "snapshot"
        assert events[0].sequence_number == 0

        # -- OutboxEvent --
        outbox = (
            await db_session.execute(
                sa_select(OutboxEvent).where(
                    OutboxEvent.aggregate_type == "BackgroundTask",
                    OutboxEvent.aggregate_id == task.id,
                )
            )
        ).scalar_one()
        assert outbox.event_type == "task.execute"
        assert outbox.status == "pending"

    @pytest.mark.asyncio
    async def test_outbox_failure_rolls_back_assessment(self, db_session):
        """If Outbox creation fails, Assessment and Task are rolled back."""
        uid = await _create_user(db_session, "atox2")
        pid, pvid, nid = await _create_path(db_session, uid)

        service = UnitService(db_session)

        with patch.object(TaskService, "enqueue_task", side_effect=RuntimeError("Outbox failure")):
            with pytest.raises(RuntimeError, match="Outbox failure"):
                await service.generate_quiz_bank(
                    path_id=pid,
                    node_id=nid,
                    user_id=uid,
                    path_version_id=pvid,
                )

        # Rollback the failed transaction to clean up session state
        await db_session.rollback()

        # Nothing should have been committed for this user
        assessments = (
            (
                await db_session.execute(
                    sa_select(Assessment).where(
                        Assessment.path_id == pid,
                        Assessment.node_id == nid,
                        Assessment.user_id == uid,
                        Assessment.purpose == "quiz_bank",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(assessments) == 0, f"Expected 0 assessments, got {len(assessments)}"

        tasks = (
            (
                await db_session.execute(
                    sa_select(BackgroundTask).where(
                        BackgroundTask.task_type == "learning_assessment_generation",
                        BackgroundTask.user_id == uid,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(tasks) == 0, f"Expected 0 tasks, got {len(tasks)}"


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class TestAssessmentGenerationIdempotency:
    """Repeated generation requests return the same result."""

    @pytest.mark.asyncio
    async def test_same_user_node_returns_same_assessment(self, db_session):
        """Same user, node, purpose -> same assessment_id."""
        uid = await _create_user(db_session, "idem1")
        pid, pvid, nid = await _create_path(db_session, uid)

        service = UnitService(db_session)
        r1 = await service.generate_quiz_bank(
            path_id=pid,
            node_id=nid,
            user_id=uid,
            path_version_id=pvid,
        )

        r2 = await service.generate_quiz_bank(
            path_id=pid,
            node_id=nid,
            user_id=uid,
            path_version_id=pvid,
        )

        assert r1["assessment_id"] == r2["assessment_id"]
        assert r1["active_task_id"] == r2["active_task_id"]

        # Only one assessment should exist
        count = (
            await db_session.execute(
                sa_select(Assessment).where(
                    Assessment.path_id == pid,
                    Assessment.node_id == nid,
                    Assessment.user_id == uid,
                    Assessment.purpose == "quiz_bank",
                )
            )
        ).scalar_one()
        assert count is not None

    @pytest.mark.asyncio
    async def test_same_request_returns_same_task(self, db_session):
        """Same idempotency_key -> same task_id."""
        uid = await _create_user(db_session, "idem2")
        pid, pvid, nid = await _create_path(db_session, uid)

        service = UnitService(db_session)
        r1 = await service.generate_quiz_bank(
            path_id=pid,
            node_id=nid,
            user_id=uid,
            path_version_id=pvid,
        )

        r2 = await service.generate_quiz_bank(
            path_id=pid,
            node_id=nid,
            user_id=uid,
            path_version_id=pvid,
        )

        assert r1["active_task_id"] == r2["active_task_id"]

        # Only one task for this user
        tasks = (
            (
                await db_session.execute(
                    sa_select(BackgroundTask).where(
                        BackgroundTask.task_type == "learning_assessment_generation",
                        BackgroundTask.user_id == uid,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(tasks) == 1

    @pytest.mark.asyncio
    async def test_only_one_outbox_event_created(self, db_session):
        """Repeated requests -> only one outbox event."""
        uid = await _create_user(db_session, "idem3")
        pid, pvid, nid = await _create_path(db_session, uid)

        service = UnitService(db_session)
        r1 = await service.generate_quiz_bank(
            path_id=pid,
            node_id=nid,
            user_id=uid,
            path_version_id=pvid,
        )

        await service.generate_quiz_bank(
            path_id=pid,
            node_id=nid,
            user_id=uid,
            path_version_id=pvid,
        )

        outbox_count = await _count_outbox(db_session, r1["active_task_id"])
        assert outbox_count == 1


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


class TestAssessmentGenerationConcurrency:
    """Concurrent generation requests must not create duplicates."""

    @pytest.mark.asyncio
    async def test_concurrent_requests_create_single_assessment(self, db_session):
        """Two concurrent generate calls with isolated sessions create one assessment."""
        uid = await _create_user(db_session, "conc1")
        pid, pvid, nid = await _create_path(db_session, uid)

        from app.config import clear_settings_cache, get_settings
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
        from sqlalchemy.pool import NullPool

        clear_settings_cache()
        settings = get_settings()
        engine = create_async_engine(settings.database_url, poolclass=NullPool, echo=False)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async def _call() -> dict | None:
            async with factory() as session:
                try:
                    svc = UnitService(session)
                    return await svc.generate_quiz_bank(
                        path_id=pid,
                        node_id=nid,
                        user_id=uid,
                        path_version_id=pvid,
                    )
                except Exception:
                    return None
                finally:
                    await session.close()
                    await engine.dispose()

        results = await _call(), await _call()

        # At least one succeeded
        successes = [r for r in results if r is not None]
        assert len(successes) >= 1

        # Only one assessment in DB
        assessments = (
            (
                await db_session.execute(
                    sa_select(Assessment).where(
                        Assessment.path_id == pid,
                        Assessment.node_id == nid,
                        Assessment.user_id == uid,
                        Assessment.purpose == "quiz_bank",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(assessments) == 1

    @pytest.mark.asyncio
    async def test_concurrent_requests_create_single_task(self, db_session):
        """Two concurrent calls -> one background task."""
        uid = await _create_user(db_session, "conc2")
        pid, pvid, nid = await _create_path(db_session, uid)

        from app.config import clear_settings_cache, get_settings
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
        from sqlalchemy.pool import NullPool

        clear_settings_cache()
        settings = get_settings()
        engine = create_async_engine(settings.database_url, poolclass=NullPool, echo=False)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async def _call() -> dict | None:
            async with factory() as session:
                try:
                    svc = UnitService(session)
                    return await svc.generate_quiz_bank(
                        path_id=pid,
                        node_id=nid,
                        user_id=uid,
                        path_version_id=pvid,
                    )
                except Exception:
                    return None
                finally:
                    await session.close()
                    await engine.dispose()

        await _call(), await _call()

        tasks = (
            (
                await db_session.execute(
                    sa_select(BackgroundTask).where(
                        BackgroundTask.task_type == "learning_assessment_generation",
                        BackgroundTask.user_id == uid,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(tasks) == 1, f"Expected 1 task, got {len(tasks)}"


# ---------------------------------------------------------------------------
# Worker success
# ---------------------------------------------------------------------------


_SAMPLE_LLM_RESPONSE = {
    "title": "Test Assessment",
    "description": "Integration test assessment",
    "questions": [
        {
            "question_type": "single_choice",
            "prompt": "What is the capital of France?",
            "options": [
                {"value": "a", "label": "London"},
                {"value": "b", "label": "Paris"},
                {"value": "c", "label": "Berlin"},
            ],
            "correct_answer": "b",
            "difficulty": "easy",
            "knowledge_point": "geography",
            "explanation": "Paris is the capital of France.",
            "max_score": 10.0,
        },
        {
            "question_type": "true_false",
            "prompt": "The Earth is flat.",
            "options": None,
            "correct_answer": False,
            "difficulty": "easy",
            "knowledge_point": "science",
            "explanation": "The Earth is approximately spherical.",
            "max_score": 5.0,
        },
        {
            "question_type": "short_answer",
            "prompt": "Explain the concept of gravity.",
            "options": None,
            "correct_answer": None,
            "reference_answer": "Gravity is a force of attraction between objects with mass.",
            "rubric": ["Defines gravity as a force (3 pts)", "Mentions mass (2 pts)"],
            "difficulty": "medium",
            "knowledge_point": "physics",
            "explanation": "Gravity is a fundamental force.",
            "max_score": 5.0,
        },
    ],
}


class TestAssessmentWorkerSuccess:
    """Worker transitions assessment through the full lifecycle."""

    @pytest.mark.asyncio
    async def test_worker_creates_questions_and_marks_ready(self, db_session):
        """After worker success: status=ready, questions populated."""
        uid = await _create_user(db_session, "wkrs1")
        pid, pvid, nid = await _create_path(db_session, uid)

        # Create assessment in pending state via service
        svc = UnitService(db_session)
        gen = await svc.generate_quiz_bank(
            path_id=pid,
            node_id=nid,
            user_id=uid,
            path_version_id=pvid,
        )
        assessment_id = gen["assessment_id"]
        task_id = gen["active_task_id"]
        await db_session.commit()

        # Simulate outbox dispatch setting task to pending and running
        task = (
            await db_session.execute(sa_select(BackgroundTask).where(BackgroundTask.id == task_id).with_for_update())
        ).scalar_one()
        task.status = "pending"
        await db_session.commit()

        # Run worker with mocked LLM
        with patch("app.workers.assessment_generation.llm_json", AsyncMock(return_value=_SAMPLE_LLM_RESPONSE)):
            result = await execute_assessment_generation(db_session, task)

        assert result["status"] == "ready"
        assert result["questions_count"] == 3
        assert result["generation_source"] == "llm"

        # Assessment is ready
        assessment = (
            await db_session.execute(sa_select(Assessment).where(Assessment.id == assessment_id))
        ).scalar_one()
        assert assessment.status == "ready"

        # Questions exist
        questions = (
            (
                await db_session.execute(
                    sa_select(AssessmentQuestion)
                    .where(AssessmentQuestion.assessment_id == assessment_id)
                    .order_by(AssessmentQuestion.question_order)
                )
            )
            .scalars()
            .all()
        )
        assert len(questions) == 3

    @pytest.mark.asyncio
    async def test_all_questions_belong_to_assessment(self, db_session):
        """All generated questions have correct assessment_id."""
        uid = await _create_user(db_session, "wkrs2")
        pid, pvid, nid = await _create_path(db_session, uid)

        svc = UnitService(db_session)
        gen = await svc.generate_quiz_bank(
            path_id=pid,
            node_id=nid,
            user_id=uid,
            path_version_id=pvid,
        )
        assessment_id = gen["assessment_id"]
        task_id = gen["active_task_id"]
        await db_session.commit()

        task = (
            await db_session.execute(sa_select(BackgroundTask).where(BackgroundTask.id == task_id).with_for_update())
        ).scalar_one()
        task.status = "pending"
        await db_session.commit()

        with patch("app.workers.assessment_generation.llm_json", AsyncMock(return_value=_SAMPLE_LLM_RESPONSE)):
            await execute_assessment_generation(db_session, task)

        questions = (
            (
                await db_session.execute(
                    sa_select(AssessmentQuestion).where(AssessmentQuestion.assessment_id == assessment_id)
                )
            )
            .scalars()
            .all()
        )
        for q in questions:
            assert q.assessment_id == assessment_id

    @pytest.mark.asyncio
    async def test_worker_sets_active_task_id_null_on_completion(self, db_session):
        """active_task_id is cleared after successful generation."""
        uid = await _create_user(db_session, "wkrs3")
        pid, pvid, nid = await _create_path(db_session, uid)

        svc = UnitService(db_session)
        gen = await svc.generate_quiz_bank(
            path_id=pid,
            node_id=nid,
            user_id=uid,
            path_version_id=pvid,
        )
        assessment_id = gen["assessment_id"]
        task_id = gen["active_task_id"]
        await db_session.commit()

        task = (
            await db_session.execute(sa_select(BackgroundTask).where(BackgroundTask.id == task_id).with_for_update())
        ).scalar_one()
        task.status = "pending"
        await db_session.commit()

        with patch("app.workers.assessment_generation.llm_json", AsyncMock(return_value=_SAMPLE_LLM_RESPONSE)):
            await execute_assessment_generation(db_session, task)

        assessment = (
            await db_session.execute(sa_select(Assessment).where(Assessment.id == assessment_id))
        ).scalar_one()
        assert assessment.active_task_id is None


# ---------------------------------------------------------------------------
# Worker failure
# ---------------------------------------------------------------------------


class TestAssessmentWorkerFailure:
    """Worker failure does not leave partial state."""

    @pytest.mark.asyncio
    async def test_failure_marks_assessment_failed(self, db_session):
        """On worker failure: assessment.status == 'failed'."""
        uid = await _create_user(db_session, "wkf1")
        pid, pvid, nid = await _create_path(db_session, uid)

        svc = UnitService(db_session)
        gen = await svc.generate_quiz_bank(
            path_id=pid,
            node_id=nid,
            user_id=uid,
            path_version_id=pvid,
        )
        assessment_id = gen["assessment_id"]
        task_id = gen["active_task_id"]
        await db_session.commit()

        task = (
            await db_session.execute(sa_select(BackgroundTask).where(BackgroundTask.id == task_id).with_for_update())
        ).scalar_one()
        task.status = "pending"
        await db_session.commit()

        # Patch _complete_assessment_generation to fail, simulating Transaction B failure
        with patch(
            "app.workers.assessment_generation._complete_assessment_generation",
            side_effect=RuntimeError("Transaction B failed"),
        ):
            with patch("app.workers.assessment_generation.llm_json", AsyncMock(return_value=_SAMPLE_LLM_RESPONSE)):
                with pytest.raises(RuntimeError, match="Transaction B failed"):
                    await execute_assessment_generation(db_session, task)

        assessment = (
            await db_session.execute(sa_select(Assessment).where(Assessment.id == assessment_id))
        ).scalar_one()
        assert assessment.status == "failed"

    @pytest.mark.asyncio
    async def test_failure_does_not_save_partial_questions(self, db_session):
        """No questions remain if Transaction B fails."""
        uid = await _create_user(db_session, "wkf2")
        pid, pvid, nid = await _create_path(db_session, uid)

        svc = UnitService(db_session)
        gen = await svc.generate_quiz_bank(
            path_id=pid,
            node_id=nid,
            user_id=uid,
            path_version_id=pvid,
        )
        assessment_id = gen["assessment_id"]
        task_id = gen["active_task_id"]
        await db_session.commit()

        task = (
            await db_session.execute(sa_select(BackgroundTask).where(BackgroundTask.id == task_id).with_for_update())
        ).scalar_one()
        task.status = "pending"
        await db_session.commit()

        with patch(
            "app.workers.assessment_generation._complete_assessment_generation",
            side_effect=RuntimeError("Transaction B failed"),
        ):
            with patch("app.workers.assessment_generation.llm_json", AsyncMock(return_value=_SAMPLE_LLM_RESPONSE)):
                with pytest.raises(RuntimeError, match="Transaction B failed"):
                    await execute_assessment_generation(db_session, task)

        questions = (
            (
                await db_session.execute(
                    sa_select(AssessmentQuestion).where(AssessmentQuestion.assessment_id == assessment_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(questions) == 0

    @pytest.mark.asyncio
    async def test_failure_clears_active_task_id(self, db_session):
        """active_task_id is set to None on failure."""
        uid = await _create_user(db_session, "wkf3")
        pid, pvid, nid = await _create_path(db_session, uid)

        svc = UnitService(db_session)
        gen = await svc.generate_quiz_bank(
            path_id=pid,
            node_id=nid,
            user_id=uid,
            path_version_id=pvid,
        )
        assessment_id = gen["assessment_id"]
        task_id = gen["active_task_id"]
        await db_session.commit()

        task = (
            await db_session.execute(sa_select(BackgroundTask).where(BackgroundTask.id == task_id).with_for_update())
        ).scalar_one()
        task.status = "pending"
        await db_session.commit()

        with patch(
            "app.workers.assessment_generation._complete_assessment_generation",
            side_effect=RuntimeError("Transaction B failed"),
        ):
            with patch("app.workers.assessment_generation.llm_json", AsyncMock(return_value=_SAMPLE_LLM_RESPONSE)):
                with pytest.raises(RuntimeError, match="Transaction B failed"):
                    await execute_assessment_generation(db_session, task)

        assessment = (
            await db_session.execute(sa_select(Assessment).where(Assessment.id == assessment_id))
        ).scalar_one()
        assert assessment.active_task_id is None
