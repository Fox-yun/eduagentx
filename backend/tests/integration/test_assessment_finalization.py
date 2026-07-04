"""Integration tests for assessment finalization with real PostgreSQL.

Verifies:
  - 65% → assessment_passed=True, node_completed=False
  - 70% boundary → node_completed=True
  - 69.99% → node_completed=False
  - Weighted mastery formula with existing progress
  - First assessment (no progress) uses fresh score, not weighted
  - Empty assessment (no answers) → 409 ASSESSMENT_NOT_SCOREABLE
  - Provisional grading skips all progress updates
  - Non-formal purpose skips all progress updates
  - Re-entry returns identical result, no duplicate snapshots/evidence
  - Version-stale assessment → 409
  - Monotonic completion: already-completed node stays completed on low score
  - MasterySnapshot uses source_id=attempt.id
  - Profile evidence rows are created and idempotent on re-entry

Run with:
    pytest tests/integration/test_assessment_finalization.py -v
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select as sa_select

from app.core.errors import ApiError
from app.models.goal import LearningGoal
from app.models.path import LearningNode, LearningPath, LearningPathVersion
from app.models.progress import LearningProgress, MasterySnapshot
from app.models.unit import Assessment, AssessmentAnswer, AssessmentAttempt, AssessmentQuestion
from app.models.user import StudentProfileEvidence, User
from app.services.assessment_finalization import finalize_assessment_attempt

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


async def _create_path(db_session, user_id: str) -> tuple[str, str, str]:
    """Create LearningGoal + LearningPath + LearningPathVersion + LearningNode."""
    gid = str(uuid.uuid4())
    goal = LearningGoal(id=gid, user_id=user_id, title="Test Goal", raw_description="Finalization integration test")
    db_session.add(goal)
    await db_session.flush()

    pid = str(uuid.uuid4())
    path = LearningPath(id=pid, user_id=user_id, goal_id=gid, status="draft")
    db_session.add(path)
    await db_session.flush()

    pvid = str(uuid.uuid4())
    pv = LearningPathVersion(id=pvid, path_id=pid, version_number=1)
    db_session.add(pv)
    await db_session.flush()

    path.active_version_id = pvid
    await db_session.flush()

    nid = str(uuid.uuid4())
    node = LearningNode(
        id=nid,
        version_id=pvid,
        title="Test Node",
        description="Test node",
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


async def _create_assessment(
    db_session, user_id: str, path_id: str, pvid: str, node_id: str, purpose: str = "formal"
) -> str:
    aid = str(uuid.uuid4())
    assessment = Assessment(
        id=aid,
        user_id=user_id,
        path_id=path_id,
        path_version_id=pvid,
        node_id=node_id,
        purpose=purpose,
        status="ready",
    )
    db_session.add(assessment)
    await db_session.commit()
    return aid


async def _create_question(
    db_session, assessment_id: str, qtype: str = "single_choice", max_score: float = 10.0
) -> str:
    qid = str(uuid.uuid4())
    q = AssessmentQuestion(
        id=qid,
        assessment_id=assessment_id,
        question_type=qtype,
        prompt="Test question?",
        correct_answer="a",
        points=10,
        max_score=max_score,
        question_order=1,
    )
    db_session.add(q)
    await db_session.commit()
    return qid


async def _create_attempt(
    db_session, assessment_id: str, user_id: str, grading_quality: str = "final", status: str = "completed"
) -> str:
    aid = str(uuid.uuid4())
    attempt = AssessmentAttempt(
        id=aid,
        assessment_id=assessment_id,
        user_id=user_id,
        status=status,
        grading_quality=grading_quality,
        score=0.0,
    )
    db_session.add(attempt)
    await db_session.commit()
    return aid


async def _create_answer(db_session, attempt_id: str, question_id: str, points_earned: float, max_score: float) -> str:
    ans_id = str(uuid.uuid4())
    ans = AssessmentAnswer(
        id=ans_id,
        attempt_id=attempt_id,
        question_id=question_id,
        answer_value='"a"',
        is_correct=points_earned >= max_score * 0.6,
        points_earned=points_earned,
        max_score=max_score,
    )
    db_session.add(ans)
    await db_session.commit()
    return ans_id


async def _load_attempt(db_session, attempt_id: str) -> AssessmentAttempt:
    return (
        await db_session.execute(sa_select(AssessmentAttempt).where(AssessmentAttempt.id == attempt_id))
    ).scalar_one()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFinalizationScoring:
    """Score percentage and pass/complete semantics."""

    @pytest.mark.asyncio
    async def test_65_pct_passed_not_completed(self, db_session):
        """65% → assessment_passed=True, node_completed=False."""
        uid = await _create_user(db_session, "fin-p65")
        pid, pvid, nid = await _create_path(db_session, uid)
        aid = await _create_assessment(db_session, uid, pid, pvid, nid)
        qid = await _create_question(db_session, aid, max_score=100.0)
        atid = await _create_attempt(db_session, aid, uid)
        await _create_answer(db_session, atid, qid, points_earned=65.0, max_score=100.0)

        result = await finalize_assessment_attempt(db_session, attempt_id=atid)
        assert result.assessment_passed is True, "65% >= 60 should pass"
        assert result.node_completed is False, "65% < 70 should not complete node"

        attempt = await _load_attempt(db_session, atid)
        assert attempt.assessment_passed is True
        assert attempt.node_completed is False
        assert attempt.finalized_at is not None
        assert attempt.progress_applied_at is not None

        # LearningProgress must exist but status is in_progress
        progress = (
            await db_session.execute(
                sa_select(LearningProgress).where(
                    LearningProgress.user_id == uid,
                    LearningProgress.node_id == nid,
                )
            )
        ).scalar_one()
        assert progress.status == "in_progress"
        assert progress.mastery == pytest.approx(65.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_70_pct_completes_node(self, db_session):
        """70% → node_completed=True, mastery >= 70."""
        uid = await _create_user(db_session, "fin-p70")
        pid, pvid, nid = await _create_path(db_session, uid)
        aid = await _create_assessment(db_session, uid, pid, pvid, nid)
        qid = await _create_question(db_session, aid, max_score=100.0)
        atid = await _create_attempt(db_session, aid, uid)
        await _create_answer(db_session, atid, qid, points_earned=70.0, max_score=100.0)

        result = await finalize_assessment_attempt(db_session, attempt_id=atid)
        assert result.assessment_passed is True
        assert result.node_completed is True

        attempt = await _load_attempt(db_session, atid)
        assert attempt.node_completed is True

        progress = (
            await db_session.execute(
                sa_select(LearningProgress).where(
                    LearningProgress.user_id == uid,
                    LearningProgress.node_id == nid,
                )
            )
        ).scalar_one()
        assert progress.status == "completed"
        assert progress.mastery == pytest.approx(70.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_69_99_not_completed(self, db_session):
        """69.99% → assessment_passed=True, node_completed=False."""
        uid = await _create_user(db_session, "fin-6999")
        pid, pvid, nid = await _create_path(db_session, uid)
        aid = await _create_assessment(db_session, uid, pid, pvid, nid)
        q1 = await _create_question(db_session, aid, max_score=10.0)
        q2 = await _create_question(db_session, aid, max_score=10.0)
        atid = await _create_attempt(db_session, aid, uid)
        await _create_answer(db_session, atid, q1, points_earned=6.0, max_score=10.0)
        await _create_answer(db_session, atid, q2, points_earned=7.998, max_score=10.0)

        result = await finalize_assessment_attempt(db_session, attempt_id=atid)
        # (6.0 + 7.998) / (10 + 10) * 100 = 13.998/20*100 = 69.99
        assert result.percentage == Decimal("69.99")
        assert result.assessment_passed is True
        assert result.node_completed is False

    @pytest.mark.asyncio
    async def test_zero_score(self, db_session):
        """0% → assessment_passed=False, node_completed=False."""
        uid = await _create_user(db_session, "fin-0")
        pid, pvid, nid = await _create_path(db_session, uid)
        aid = await _create_assessment(db_session, uid, pid, pvid, nid)
        qid = await _create_question(db_session, aid, max_score=100.0)
        atid = await _create_attempt(db_session, aid, uid)
        await _create_answer(db_session, atid, qid, points_earned=0.0, max_score=100.0)

        result = await finalize_assessment_attempt(db_session, attempt_id=atid)
        assert result.assessment_passed is False
        assert result.node_completed is False
        assert result.percentage == Decimal("0.00")

    @pytest.mark.asyncio
    async def test_empty_assessment_rejected(self, db_session):
        """No answers → ASSESSMENT_NOT_SCOREABLE (409)."""
        uid = await _create_user(db_session, "fin-empty")
        pid, pvid, nid = await _create_path(db_session, uid)
        aid = await _create_assessment(db_session, uid, pid, pvid, nid)
        atid = await _create_attempt(db_session, aid, uid)

        with pytest.raises(ApiError) as exc:
            await finalize_assessment_attempt(db_session, attempt_id=atid)
        assert exc.value.code == "ASSESSMENT_NOT_SCOREABLE"

    @pytest.mark.asyncio
    async def test_provisional_skips_progress(self, db_session):
        """Provisional → finalized_at set, no progress/snapshot/evidence."""
        uid = await _create_user(db_session, "fin-prov")
        pid, pvid, nid = await _create_path(db_session, uid)
        aid = await _create_assessment(db_session, uid, pid, pvid, nid)
        qid = await _create_question(db_session, aid, max_score=100.0)
        atid = await _create_attempt(db_session, aid, uid, grading_quality="provisional")
        await _create_answer(db_session, atid, qid, points_earned=65.0, max_score=100.0)

        result = await finalize_assessment_attempt(db_session, attempt_id=atid)
        assert result.grading_quality == "provisional"
        assert not result.mastery_updated

        attempt = await _load_attempt(db_session, atid)
        assert attempt.finalized_at is not None
        assert attempt.progress_applied_at is None  # never applied

        # No progress or snapshot created
        progress = (
            await db_session.execute(
                sa_select(LearningProgress).where(
                    LearningProgress.user_id == uid,
                    LearningProgress.node_id == nid,
                )
            )
        ).scalar_one_or_none()
        assert progress is None

    @pytest.mark.asyncio
    async def test_practice_skips_progress(self, db_session):
        """Non-formal (practice) → finalized_at set, no progress update."""
        uid = await _create_user(db_session, "fin-prac")
        pid, pvid, nid = await _create_path(db_session, uid)
        aid = await _create_assessment(db_session, uid, pid, pvid, nid, purpose="practice")
        qid = await _create_question(db_session, aid, max_score=100.0)
        atid = await _create_attempt(db_session, aid, uid)
        await _create_answer(db_session, atid, qid, points_earned=85.0, max_score=100.0)

        result = await finalize_assessment_attempt(db_session, attempt_id=atid)
        assert result.grading_quality == "final"
        assert not result.mastery_updated

        attempt = await _load_attempt(db_session, atid)
        assert attempt.finalized_at is not None
        assert attempt.progress_applied_at is None

        progress = (
            await db_session.execute(
                sa_select(LearningProgress).where(
                    LearningProgress.user_id == uid,
                    LearningProgress.node_id == nid,
                )
            )
        ).scalar_one_or_none()
        assert progress is None


class TestMasteryFormula:
    """Weighted mastery calculation."""

    @pytest.mark.asyncio
    async def test_first_assessment_uses_fresh_score(self, db_session):
        """No existing progress → mastery_after = percentage (not weighted)."""
        uid = await _create_user(db_session, "fin-first")
        pid, pvid, nid = await _create_path(db_session, uid)
        aid = await _create_assessment(db_session, uid, pid, pvid, nid)
        qid = await _create_question(db_session, aid, max_score=100.0)
        atid = await _create_attempt(db_session, aid, uid)
        await _create_answer(db_session, atid, qid, points_earned=85.0, max_score=100.0)

        result = await finalize_assessment_attempt(db_session, attempt_id=atid)
        assert result.mastery_before == Decimal("0")
        assert result.mastery_after == Decimal("85.00")

    @pytest.mark.asyncio
    async def test_weighted_formula_with_existing_progress(self, db_session):
        """Existing mastery=50, new score=100 → 50*0.3 + 100*0.7 = 85."""
        uid = await _create_user(db_session, "fin-wgt")
        pid, pvid, nid = await _create_path(db_session, uid)

        # Create existing progress with mastery=50
        progress = LearningProgress(
            id=str(uuid.uuid4()),
            user_id=uid,
            path_id=pid,
            node_id=nid,
            status="in_progress",
            mastery=50.0,
            attempts=1,
        )
        db_session.add(progress)
        await db_session.commit()

        aid = await _create_assessment(db_session, uid, pid, pvid, nid)
        qid = await _create_question(db_session, aid, max_score=100.0)
        atid = await _create_attempt(db_session, aid, uid)
        await _create_answer(db_session, atid, qid, points_earned=100.0, max_score=100.0)

        result = await finalize_assessment_attempt(db_session, attempt_id=atid)
        assert result.mastery_before == Decimal("50.00")
        assert result.mastery_after == Decimal("85.00")

    @pytest.mark.asyncio
    async def test_existing_mastery_zero_still_uses_weighted(self, db_session):
        """Progress exists but mastery=0 → still uses weighted formula (not fresh)."""
        uid = await _create_user(db_session, "fin-m0")
        pid, pvid, nid = await _create_path(db_session, uid)

        progress = LearningProgress(
            id=str(uuid.uuid4()),
            user_id=uid,
            path_id=pid,
            node_id=nid,
            status="in_progress",
            mastery=0.0,
            attempts=1,
        )
        db_session.add(progress)
        await db_session.commit()

        aid = await _create_assessment(db_session, uid, pid, pvid, nid)
        qid = await _create_question(db_session, aid, max_score=100.0)
        atid = await _create_attempt(db_session, aid, uid)
        await _create_answer(db_session, atid, qid, points_earned=80.0, max_score=100.0)

        result = await finalize_assessment_attempt(db_session, attempt_id=atid)
        # 0.0 * 0.3 + 80 * 0.7 = 56.00 (NOT 80)
        assert result.mastery_after == Decimal("56.00")

    @pytest.mark.asyncio
    async def test_low_score_does_not_downgrade_completed_node(self, db_session):
        """Already completed node + low score → stays completed (monotonic)."""
        uid = await _create_user(db_session, "fin-mono")
        pid, pvid, nid = await _create_path(db_session, uid)

        # Set up already completed progress
        progress = LearningProgress(
            id=str(uuid.uuid4()),
            user_id=uid,
            path_id=pid,
            node_id=nid,
            status="completed",
            mastery=85.0,
            attempts=1,
            completed_at=datetime.now(UTC),
        )
        db_session.add(progress)
        await db_session.commit()

        aid = await _create_assessment(db_session, uid, pid, pvid, nid)
        qid = await _create_question(db_session, aid, max_score=100.0)
        atid = await _create_attempt(db_session, aid, uid)
        await _create_answer(db_session, atid, qid, points_earned=30.0, max_score=100.0)

        result = await finalize_assessment_attempt(db_session, attempt_id=atid)
        # 85*0.3 + 30*0.7 = 25.5 + 21 = 46.5 — even though mastery dropped
        assert result.mastery_after == Decimal("46.50")
        assert result.node_completed is False  # this attempt didn't pass

        # But the node stays completed!
        progress = (
            await db_session.execute(
                sa_select(LearningProgress).where(
                    LearningProgress.user_id == uid,
                    LearningProgress.node_id == nid,
                )
            )
        ).scalar_one()
        assert progress.status == "completed"


class TestVersionAndSafety:
    """Version validation and error handling."""

    @pytest.mark.asyncio
    async def test_version_stale_rejected(self, db_session):
        """Assessment with different path_version_id → 409."""
        uid = await _create_user(db_session, "fin-stale")
        pid, pvid, nid = await _create_path(db_session, uid)
        # Create assessment with wrong version
        wrong_pvid = str(uuid.uuid4())
        aid = await _create_assessment(db_session, uid, pid, wrong_pvid, nid)
        qid = await _create_question(db_session, aid, max_score=100.0)
        atid = await _create_attempt(db_session, aid, uid)
        await _create_answer(db_session, atid, qid, points_earned=90.0, max_score=100.0)

        with pytest.raises(ApiError) as exc:
            await finalize_assessment_attempt(db_session, attempt_id=atid)
        assert exc.value.code == "ASSESSMENT_VERSION_STALE"

    @pytest.mark.asyncio
    async def test_reentry_idempotent(self, db_session):
        """Calling finalize twice returns same result, no duplicate snapshots."""
        uid = await _create_user(db_session, "fin-re2")
        pid, pvid, nid = await _create_path(db_session, uid)
        aid = await _create_assessment(db_session, uid, pid, pvid, nid)
        qid = await _create_question(db_session, aid, max_score=100.0)
        atid = await _create_attempt(db_session, aid, uid)
        await _create_answer(db_session, atid, qid, points_earned=85.0, max_score=100.0)

        r1 = await finalize_assessment_attempt(db_session, attempt_id=atid)
        r2 = await finalize_assessment_attempt(db_session, attempt_id=atid)

        # Same values
        assert r1.assessment_passed == r2.assessment_passed
        assert r1.node_completed == r2.node_completed
        assert r1.percentage == r2.percentage
        assert r1.mastery_after == r2.mastery_after

        # No duplicate snapshots
        snapshots = (
            (
                await db_session.execute(
                    sa_select(MasterySnapshot).where(
                        MasterySnapshot.source_type == "assessment_attempt",
                        MasterySnapshot.source_id == atid,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(snapshots) == 1

        # No duplicate evidence
        evidence = (
            (
                await db_session.execute(
                    sa_select(StudentProfileEvidence).where(
                        StudentProfileEvidence.evidence_type == "assessment_attempt",
                        StudentProfileEvidence.evidence_id == atid,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(evidence) == 4  # 2 from _record_assessment_evidence + 2 from apply_assessment_evidence

        # Attempts counter increased exactly once
        progress = (
            await db_session.execute(
                sa_select(LearningProgress).where(
                    LearningProgress.user_id == uid,
                    LearningProgress.node_id == nid,
                )
            )
        ).scalar_one()
        assert progress.attempts == 1


class TestSnapshotAndEvidence:
    """Mastery snapshots and profile evidence correctness."""

    @pytest.mark.asyncio
    async def test_snapshot_uses_attempt_id(self, db_session):
        """MasterySnapshot source_id = attempt.id, source_type = assessment_attempt."""
        uid = await _create_user(db_session, "fin-snap")
        pid, pvid, nid = await _create_path(db_session, uid)
        aid = await _create_assessment(db_session, uid, pid, pvid, nid)
        qid = await _create_question(db_session, aid, max_score=100.0)
        atid = await _create_attempt(db_session, aid, uid)
        await _create_answer(db_session, atid, qid, points_earned=85.0, max_score=100.0)

        await finalize_assessment_attempt(db_session, attempt_id=atid)

        snapshot = (
            await db_session.execute(
                sa_select(MasterySnapshot).where(
                    MasterySnapshot.source_type == "assessment_attempt",
                    MasterySnapshot.source_id == atid,
                )
            )
        ).scalar_one_or_none()
        assert snapshot is not None
        assert snapshot.source_id == atid

    @pytest.mark.asyncio
    async def test_profile_evidence_created(self, db_session):
        """Profile evidence rows for concept_grasp and knowledge_depth."""
        uid = await _create_user(db_session, "fin-ev")
        pid, pvid, nid = await _create_path(db_session, uid)
        aid = await _create_assessment(db_session, uid, pid, pvid, nid)
        qid = await _create_question(db_session, aid, max_score=100.0)
        atid = await _create_attempt(db_session, aid, uid)
        await _create_answer(db_session, atid, qid, points_earned=85.0, max_score=100.0)

        result = await finalize_assessment_attempt(db_session, attempt_id=atid)
        assert len(result.profile_evidence_ids) == 2

        evidence = (
            (
                await db_session.execute(
                    sa_select(StudentProfileEvidence).where(
                        StudentProfileEvidence.evidence_id == atid,
                    )
                )
            )
            .scalars()
            .all()
        )
        # 2 from _record_assessment_evidence (concept_grasp, knowledge_depth)
        # + 2 from apply_assessment_evidence (problem_solving, practice_ability)
        assert len(evidence) == 4
        dimensions = {e.dimension for e in evidence}
        assert dimensions == {"concept_grasp", "knowledge_depth", "problem_solving", "practice_ability"}

    @pytest.mark.asyncio
    async def test_profile_evidence_question_count(self, db_session):
        """evidence_metadata.question_count stores question count, not total score."""
        uid = await _create_user(db_session, "fin-qc")
        pid, pvid, nid = await _create_path(db_session, uid)
        aid = await _create_assessment(db_session, uid, pid, pvid, nid)
        q1 = await _create_question(db_session, aid, max_score=10.0)
        q2 = await _create_question(db_session, aid, max_score=10.0)
        atid = await _create_attempt(db_session, aid, uid)
        await _create_answer(db_session, atid, q1, points_earned=8.0, max_score=10.0)
        await _create_answer(db_session, atid, q2, points_earned=7.0, max_score=10.0)

        await finalize_assessment_attempt(db_session, attempt_id=atid)

        evidence = (
            (
                await db_session.execute(
                    sa_select(StudentProfileEvidence).where(
                        StudentProfileEvidence.evidence_id == atid,
                    )
                )
            )
            .scalars()
            .all()
        )
        # Only evidence from _record_assessment_evidence has question_count
        record_evidence = [e for e in evidence if "question_count" in (e.evidence_metadata or {})]
        for e in record_evidence:
            assert e.evidence_metadata["question_count"] == 2
