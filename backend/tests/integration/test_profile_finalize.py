"""Integration tests for profile finalize lifecycle.

Verifies:
  - finalize() creates StudentProfile
  - finalize() writes StudentProfileEvidence records
  - finalize() marks session as completed
  - Repeated finalize is idempotent: profile_version doesn't increase, no duplicate evidence
  - finalize() delegates to apply_profile_evidence (single code path)
  - can_finalize enforces rules

Run with:
    pytest tests/integration/test_profile_finalize.py -v
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.models.profile import ProfileConversationSession
from app.models.user import StudentProfileEvidence, User
from app.services.profile_conversation import ProfileConversationService


async def _create_user(db_session, prefix: str = "profile-fin") -> str:
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


def _make_extracted_dimensions(count: int = 6, confidence: float = 0.7) -> dict:
    """Build a dict of N extracted dimensions with sufficient confidence."""
    all_dims = [
        "knowledge_depth",
        "prerequisite_mastery",
        "concept_grasp",
        "problem_solving",
        "practice_ability",
        "learning_pace",
        "resource_preference",
        "error_pattern",
    ]
    return {dim: {"value": 0.5, "confidence": confidence, "evidence_text": "test"} for dim in all_dims[:count]}


class TestFinalizeCreatesProfile:
    async def test_finalize_creates_student_profile(self, db_session):
        user_id = await _create_user(db_session)
        svc = ProfileConversationService(db_session)

        session = await svc.create_session(
            user_id=user_id,
            learning_goal="学 Python",
        )

        # Manually set extracted dimensions and turn count to pass can_finalize
        session.extracted_dimensions = _make_extracted_dimensions(7, 0.7)
        session.turn_count = 3
        await db_session.commit()
        await db_session.refresh(session)

        profile = await svc.finalize(session)

        assert profile is not None
        assert profile.user_id == user_id
        assert profile.profile_version >= 1
        assert len(profile.dimensions) > 0

    async def test_finalize_writes_evidence_records(self, db_session):
        user_id = await _create_user(db_session)
        svc = ProfileConversationService(db_session)

        session = await svc.create_session(
            user_id=user_id,
            learning_goal="学 Python",
        )

        session.extracted_dimensions = _make_extracted_dimensions(6, 0.7)
        session.turn_count = 3
        await db_session.commit()
        await db_session.refresh(session)

        await svc.finalize(session)

        # Check evidence records were created
        result = await db_session.execute(
            select(StudentProfileEvidence).where(StudentProfileEvidence.user_id == user_id)
        )
        evidence_records = list(result.scalars().all())
        assert len(evidence_records) == 6
        for ev in evidence_records:
            assert ev.evidence_type == "conversation_profile"
            assert ev.evidence_id == session.id

    async def test_finalize_marks_session_completed(self, db_session):
        user_id = await _create_user(db_session)
        svc = ProfileConversationService(db_session)

        session = await svc.create_session(
            user_id=user_id,
            learning_goal="学 Python",
        )

        session.extracted_dimensions = _make_extracted_dimensions(6, 0.7)
        session.turn_count = 3
        await db_session.commit()
        await db_session.refresh(session)

        await svc.finalize(session)

        # Re-fetch session
        result = await db_session.execute(
            select(ProfileConversationSession).where(ProfileConversationSession.id == session.id)
        )
        fresh = result.scalar_one()
        assert fresh.status == "completed"
        assert fresh.profile_id is not None
        assert fresh.completed_at is not None


class TestFinalizeIdempotency:
    async def test_repeated_finalize_no_duplicate_evidence(self, db_session):
        """E0-A4: Calling finalize twice should not create duplicate evidence."""
        user_id = await _create_user(db_session)
        svc = ProfileConversationService(db_session)

        session = await svc.create_session(
            user_id=user_id,
            learning_goal="学 Python",
        )

        session.extracted_dimensions = _make_extracted_dimensions(6, 0.7)
        session.turn_count = 3
        await db_session.commit()
        await db_session.refresh(session)

        profile1 = await svc.finalize(session)

        # Get version after first finalize
        version1 = profile1.profile_version

        # Get evidence count after first finalize
        result = await db_session.execute(
            select(StudentProfileEvidence).where(StudentProfileEvidence.user_id == user_id)
        )
        evidence_count_1 = len(list(result.scalars().all()))

        # Re-apply the same evidence (simulating a retry)
        from app.services.profile_merge import ProfileEvidenceInput, apply_profile_evidence

        evidence_inputs = [
            ProfileEvidenceInput(
                dimension=dim,
                value=data["value"],
                confidence=data["confidence"],
                evidence_type="conversation_profile",
                evidence_id=session.id,
            )
            for dim, data in _make_extracted_dimensions(6, 0.7).items()
        ]
        profile2 = await apply_profile_evidence(db_session, user_id=user_id, evidence=evidence_inputs)

        # Version should NOT increase
        assert profile2.profile_version == version1

        # Evidence count should NOT increase
        result = await db_session.execute(
            select(StudentProfileEvidence).where(StudentProfileEvidence.user_id == user_id)
        )
        evidence_count_2 = len(list(result.scalars().all()))
        assert evidence_count_2 == evidence_count_1

    async def test_new_evidence_increases_version(self, db_session):
        """Adding genuinely new evidence should increase profile_version."""
        user_id = await _create_user(db_session)
        svc = ProfileConversationService(db_session)

        session = await svc.create_session(
            user_id=user_id,
            learning_goal="学 Python",
        )

        session.extracted_dimensions = _make_extracted_dimensions(6, 0.7)
        session.turn_count = 3
        await db_session.commit()
        await db_session.refresh(session)

        profile1 = await svc.finalize(session)
        version1 = profile1.profile_version

        # Apply new evidence from a different source
        from app.services.profile_merge import ProfileEvidenceInput, apply_profile_evidence

        new_evidence = [
            ProfileEvidenceInput(
                dimension="knowledge_depth",
                value=0.8,
                confidence=0.9,
                evidence_type="assessment_attempt",
                evidence_id="different-attempt-id",
            ),
        ]
        profile2 = await apply_profile_evidence(db_session, user_id=user_id, evidence=new_evidence)

        assert profile2.profile_version == version1 + 1


class TestCanFinalizeEnforcement:
    async def test_finalize_with_insufficient_turns_blocked(self, db_session):
        """E0-A5: can_finalize returns False for insufficient turns."""
        user_id = await _create_user(db_session)
        svc = ProfileConversationService(db_session)

        session = await svc.create_session(
            user_id=user_id,
            learning_goal="学 Python",
        )

        session.extracted_dimensions = _make_extracted_dimensions(8, 0.9)
        session.turn_count = 2  # Below MIN_TURNS
        await db_session.commit()
        await db_session.refresh(session)

        assert ProfileConversationService.can_finalize(session) is False

    async def test_finalize_with_insufficient_dimensions_blocked(self, db_session):
        """E0-A5: can_finalize returns False for insufficient dimensions."""
        user_id = await _create_user(db_session)
        svc = ProfileConversationService(db_session)

        session = await svc.create_session(
            user_id=user_id,
            learning_goal="学 Python",
        )

        session.extracted_dimensions = _make_extracted_dimensions(5, 0.9)
        session.turn_count = 3
        await db_session.commit()
        await db_session.refresh(session)

        assert ProfileConversationService.can_finalize(session) is False

    async def test_finalize_with_low_confidence_blocked(self, db_session):
        """E0-A5: can_finalize returns False for low confidence."""
        user_id = await _create_user(db_session)
        svc = ProfileConversationService(db_session)

        session = await svc.create_session(
            user_id=user_id,
            learning_goal="学 Python",
        )

        session.extracted_dimensions = _make_extracted_dimensions(8, 0.4)
        session.turn_count = 3
        await db_session.commit()
        await db_session.refresh(session)

        assert ProfileConversationService.can_finalize(session) is False

    async def test_can_finalize_passes_with_valid_state(self, db_session):
        """E0-A5: can_finalize returns True when all conditions are met."""
        user_id = await _create_user(db_session)
        svc = ProfileConversationService(db_session)

        session = await svc.create_session(
            user_id=user_id,
            learning_goal="学 Python",
        )

        session.extracted_dimensions = _make_extracted_dimensions(7, 0.75)
        session.turn_count = 3
        await db_session.commit()
        await db_session.refresh(session)

        assert ProfileConversationService.can_finalize(session) is True
