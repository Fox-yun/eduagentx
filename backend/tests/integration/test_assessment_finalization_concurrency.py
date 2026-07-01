"""Concurrency tests for assessment finalization with real PostgreSQL.

Verifies:
  - Same-node concurrent finalization: two attempts finishing at the same time
    do not lose mastery updates and both record correctly.
  - DAG unlock: multiple prerequisite nodes completing concurrently always
    unlock the successor (all-prerequisites-met strategy).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import clear_settings_cache, get_settings
from app.core.errors import ApiError
from app.models.goal import LearningGoal
from app.models.path import LearningEdge, LearningNode, LearningPath, LearningPathVersion
from app.models.progress import LearningProgress, MasterySnapshot
from app.models.unit import Assessment, AssessmentAnswer, AssessmentAttempt, AssessmentQuestion
from app.models.user import User
from app.services.assessment_finalization import finalize_assessment_attempt

# ---------------------------------------------------------------------------
# Shared seed helpers (inline — no shared state between sessions)
# ---------------------------------------------------------------------------


async def _seed_concurrent_test(db_url: str) -> dict:
    """Seed data shared by concurrent test sessions. Returns IDs."""
    clear_settings_cache()
    engine = create_async_engine(db_url, poolclass=NullPool, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        uid = str(uuid.uuid4())
        user = User(
            id=uid,
            email=f"con-{uid[:8]}@t.example.com",
            email_normalized=f"con-{uid[:8]}@t.example.com",
            display_name="concurrent",
            password_hash="hash",
            status="active",
            email_verified_at=datetime.now(UTC),
        )
        session.add(user)
        await session.flush()

        gid = str(uuid.uuid4())
        session.add(LearningGoal(id=gid, user_id=uid, title="Concurrent Test Goal", raw_description="Concurrency test"))
        await session.flush()

        pid = str(uuid.uuid4())
        pvid = str(uuid.uuid4())
        nid = str(uuid.uuid4())

        session.add(LearningPath(id=pid, user_id=uid, goal_id=gid, status="draft"))
        await session.flush()
        session.add(LearningPathVersion(id=pvid, path_id=pid, version_number=1))
        await session.flush()

        path = (await session.execute(sa_select(LearningPath).where(LearningPath.id == pid))).scalar_one()
        path.active_version_id = pvid
        await session.flush()

        session.add(
            LearningNode(
                id=nid,
                version_id=pvid,
                title="Concurrent Node",
                description="Node for concurrent finalization",
                node_order=1,
                level=1,
                difficulty="beginner",
                estimated_minutes=30,
                status="available",
                content_status="ready",
            )
        )
        await session.flush()

        aid = str(uuid.uuid4())
        session.add(
            Assessment(
                id=aid, user_id=uid, path_id=pid, path_version_id=pvid, node_id=nid, purpose="formal", status="ready"
            )
        )
        await session.flush()

        qid = str(uuid.uuid4())
        session.add(
            AssessmentQuestion(
                id=qid,
                assessment_id=aid,
                question_type="single_choice",
                prompt="Test?",
                correct_answer="a",
                points=10,
                max_score=100.0,
                question_order=1,
            )
        )
        await session.flush()

        # Create two attempts, both completed, both grading_quality="final"
        atid1 = str(uuid.uuid4())
        atid2 = str(uuid.uuid4())
        session.add(
            AssessmentAttempt(
                id=atid1, assessment_id=aid, user_id=uid, status="completed", grading_quality="final", score=0.0
            )
        )
        session.add(
            AssessmentAttempt(
                id=atid2, assessment_id=aid, user_id=uid, status="completed", grading_quality="final", score=0.0
            )
        )
        await session.flush()

        # Answer row for each attempt: attempt1=65, attempt2=85
        session.add(
            AssessmentAnswer(
                id=str(uuid.uuid4()),
                attempt_id=atid1,
                question_id=qid,
                answer_value='"a"',
                is_correct=True,
                points_earned=65.0,
                max_score=100.0,
            )
        )
        session.add(
            AssessmentAnswer(
                id=str(uuid.uuid4()),
                attempt_id=atid2,
                question_id=qid,
                answer_value='"a"',
                is_correct=True,
                points_earned=85.0,
                max_score=100.0,
            )
        )
        await session.commit()

        data = dict(db_url=db_url, user_id=uid, path_id=pid, node_id=nid, attempt1_id=atid1, attempt2_id=atid2)

    await engine.dispose()
    return data


async def _seed_dag_test(db_url: str) -> dict:
    """Seed a simple DAG: A ─┐
                                 ├→ C
                              B ─┘
    Both A and B will have completed attempts.
    """
    clear_settings_cache()
    engine = create_async_engine(db_url, poolclass=NullPool, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        uid = str(uuid.uuid4())
        user = User(
            id=uid,
            email=f"dag-{uid[:8]}@t.example.com",
            email_normalized=f"dag-{uid[:8]}@t.example.com",
            display_name="dag-concurrent",
            password_hash="hash",
            status="active",
            email_verified_at=datetime.now(UTC),
        )
        session.add(user)
        await session.flush()

        gid = str(uuid.uuid4())
        session.add(
            LearningGoal(id=gid, user_id=uid, title="DAG Test Goal", raw_description="DAG concurrent unlock test")
        )
        await session.flush()

        pid = str(uuid.uuid4())
        pvid = str(uuid.uuid4())
        session.add(LearningPath(id=pid, user_id=uid, goal_id=gid, status="draft"))
        await session.flush()
        session.add(LearningPathVersion(id=pvid, path_id=pid, version_number=1))
        await session.flush()

        path = (await session.execute(sa_select(LearningPath).where(LearningPath.id == pid))).scalar_one()
        path.active_version_id = pvid
        await session.flush()

        nid_a = str(uuid.uuid4())
        nid_b = str(uuid.uuid4())
        nid_c = str(uuid.uuid4())

        for nid, title in [(nid_a, "Node A"), (nid_b, "Node B"), (nid_c, "Node C")]:
            session.add(
                LearningNode(
                    id=nid,
                    version_id=pvid,
                    title=title,
                    description=title,
                    node_order=1,
                    level=1,
                    difficulty="beginner",
                    estimated_minutes=30,
                    status="available",
                    content_status="ready",
                )
            )
        await session.flush()

        # Edges: A→C, B→C
        session.add(LearningEdge(id=str(uuid.uuid4()), version_id=pvid, source_node_id=nid_a, target_node_id=nid_c))
        session.add(LearningEdge(id=str(uuid.uuid4()), version_id=pvid, source_node_id=nid_b, target_node_id=nid_c))
        await session.flush()

        # Assessment for node A
        aid_a = str(uuid.uuid4())
        session.add(
            Assessment(
                id=aid_a,
                user_id=uid,
                path_id=pid,
                path_version_id=pvid,
                node_id=nid_a,
                purpose="formal",
                status="ready",
            )
        )

        # Assessment for node B
        aid_b = str(uuid.uuid4())
        session.add(
            Assessment(
                id=aid_b,
                user_id=uid,
                path_id=pid,
                path_version_id=pvid,
                node_id=nid_b,
                purpose="formal",
                status="ready",
            )
        )
        await session.flush()

        # One question per assessment
        for aid, (qid,) in [(aid_a, (str(uuid.uuid4()),)), (aid_b, (str(uuid.uuid4()),))]:
            session.add(
                AssessmentQuestion(
                    id=qid,
                    assessment_id=aid,
                    question_type="single_choice",
                    prompt="Test?",
                    correct_answer="a",
                    points=10,
                    max_score=100.0,
                    question_order=1,
                )
            )
            await session.flush()

        # Attempts for A and B (both completed, both 85% — passes mastery)
        atid_a = str(uuid.uuid4())
        atid_b = str(uuid.uuid4())
        session.add(
            AssessmentAttempt(
                id=atid_a, assessment_id=aid_a, user_id=uid, status="completed", grading_quality="final", score=0.0
            )
        )
        session.add(
            AssessmentAttempt(
                id=atid_b, assessment_id=aid_b, user_id=uid, status="completed", grading_quality="final", score=0.0
            )
        )
        await session.flush()

        # Answers (85% — passes both assessment and mastery)
        session.add(
            AssessmentAnswer(
                id=str(uuid.uuid4()),
                attempt_id=atid_a,
                question_id=(
                    await session.execute(
                        sa_select(AssessmentQuestion).where(AssessmentQuestion.assessment_id == aid_a)
                    )
                )
                .scalar_one()
                .id,
                answer_value='"a"',
                is_correct=True,
                points_earned=85.0,
                max_score=100.0,
            )
        )
        session.add(
            AssessmentAnswer(
                id=str(uuid.uuid4()),
                attempt_id=atid_b,
                question_id=(
                    await session.execute(
                        sa_select(AssessmentQuestion).where(AssessmentQuestion.assessment_id == aid_b)
                    )
                )
                .scalar_one()
                .id,
                answer_value='"a"',
                is_correct=True,
                points_earned=85.0,
                max_score=100.0,
            )
        )
        await session.commit()

        data = dict(
            db_url=db_url,
            user_id=uid,
            path_id=pid,
            node_a=nid_a,
            node_b=nid_b,
            node_c=nid_c,
            attempt_a=atid_a,
            attempt_b=atid_b,
        )

    await engine.dispose()
    return data


async def _finalize_in_session(db_url: str, attempt_id: str) -> dict | None:
    """Call finalize_assessment_attempt in its own session."""
    clear_settings_cache()
    engine = create_async_engine(db_url, poolclass=NullPool, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        try:
            result = await finalize_assessment_attempt(session, attempt_id=attempt_id)
            await session.commit()
            return {
                "assessment_passed": result.assessment_passed,
                "node_completed": result.node_completed,
                "mastery_before": float(result.mastery_before),
                "mastery_after": float(result.mastery_after),
                "mastery_updated": result.mastery_updated,
            }
        except ApiError as e:
            await session.rollback()
            return {"error": e.code}
        except Exception as e:
            await session.rollback()
            return {"error": str(e)}
        finally:
            await session.close()
            await engine.dispose()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestConcurrentFinalization:
    """Concurrent finalization of two attempts on the same path+node."""

    @pytest.mark.asyncio
    async def test_concurrent_mastery_no_lost_update(self):
        """Two concurrent finalizations produce correct cumulative mastery."""
        db_url = get_settings().database_url
        data = await _seed_concurrent_test(db_url)

        # Fire both concurrently
        r1, r2 = await asyncio.gather(
            _finalize_in_session(db_url, data["attempt1_id"]),
            _finalize_in_session(db_url, data["attempt2_id"]),
        )

        assert r1 is not None and r2 is not None
        assert r1.get("error") is None, f"Attempt 1 failed: {r1}"
        assert r2.get("error") is None, f"Attempt 2 failed: {r2}"

        # After both complete, read the final progress state
        engine = create_async_engine(db_url, poolclass=NullPool, echo=False)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with factory() as session:
            progress = (
                await session.execute(
                    sa_select(LearningProgress).where(
                        LearningProgress.user_id == data["user_id"],
                        LearningProgress.node_id == data["node_id"],
                    )
                )
            ).scalar_one()
            final_mastery = Decimal(str(progress.mastery))
            await session.close()
        await engine.dispose()

        # attempt1 (65): no existing progress → mastery_after = 65.00
        # attempt2 (85): existing progress with mastery=65 → 65*0.3 + 85*0.7 = 19.5 + 59.5 = 79.00
        # The order depends on which acquires the path lock first.
        # Both orders produce valid results:
        #   Order A (65 then 85): final = 65*0.3 + 85*0.7 = 79.00
        #   Order B (85 then 65): final = 85*0.3 + 65*0.7 = 25.5 + 45.5 = 71.00
        assert final_mastery in (Decimal("79.00"), Decimal("71.00")), f"Unexpected final mastery {final_mastery}"

        # Both attempts must have recorded their contribution
        engine2 = create_async_engine(db_url, poolclass=NullPool, echo=False)
        factory2 = async_sessionmaker(engine2, class_=AsyncSession, expire_on_commit=False)
        async with factory2() as session:
            snapshots = (
                (
                    await session.execute(
                        sa_select(MasterySnapshot).where(
                            MasterySnapshot.user_id == data["user_id"],
                            MasterySnapshot.node_id == data["node_id"],
                        )
                    )
                )
                .scalars()
                .all()
            )
            await session.close()
        await engine2.dispose()
        assert len(snapshots) == 2, "Both attempts must create a snapshot"

        assert progress.attempts == 2, "Both attempts counted"


class TestDAGConcurrentUnlock:
    """Concurrent completion of multiple prereqs always unlocks successor."""

    @pytest.mark.asyncio
    async def test_concurrent_prereqs_unlock_successor(self):
        """A and B both complete concurrently → C is always available."""
        db_url = get_settings().database_url
        data = await _seed_dag_test(db_url)

        # Fire both finalizations concurrently
        ra, rb = await asyncio.gather(
            _finalize_in_session(db_url, data["attempt_a"]),
            _finalize_in_session(db_url, data["attempt_b"]),
        )

        assert ra is not None and rb is not None
        assert ra.get("error") is None, f"Attempt A failed: {ra}"
        assert rb.get("error") is None, f"Attempt B failed: {rb}"

        # Read final state
        engine = create_async_engine(db_url, poolclass=NullPool, echo=False)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with factory() as session:
            progress_c = (
                await session.execute(
                    sa_select(LearningProgress).where(
                        LearningProgress.user_id == data["user_id"],
                        LearningProgress.node_id == data["node_c"],
                    )
                )
            ).scalar_one_or_none()
            await session.close()
        await engine.dispose()

        assert progress_c is not None, "Node C must have a progress record"
        assert progress_c.status == "available", (
            f"Node C must be unlocked after both A and B complete. Got status={progress_c.status}"
        )
