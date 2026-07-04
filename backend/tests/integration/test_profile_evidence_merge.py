"""Integration tests for profile evidence merge idempotency.

Verifies:
  - Duplicate evidence (same evidence_type + evidence_id + dimension) is not re-merged
  - profile_version only increases when genuinely new evidence is added
  - Evidence records are not duplicated
  - Multiple evidence types from different sources all merge correctly

Run with:
    pytest tests/integration/test_profile_evidence_merge.py -v
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.models.user import StudentProfileEvidence, User
from app.services.profile_merge import (
    ProfileEvidenceInput,
    apply_assessment_evidence,
    apply_diagnostic_evidence,
    apply_profile_evidence,
)


async def _create_user(db_session, prefix: str = "profile-merge") -> str:
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


class TestEvidenceIdempotency:
    async def test_same_evidence_not_remerged(self, db_session):
        """E0-A4: Applying the same evidence twice should not re-merge."""
        user_id = await _create_user(db_session)

        evidence = [
            ProfileEvidenceInput(
                dimension="knowledge_depth",
                value=0.6,
                confidence=0.8,
                evidence_type="conversation_profile",
                evidence_id="session-1",
            ),
        ]

        profile1 = await apply_profile_evidence(db_session, user_id=user_id, evidence=evidence)
        version1 = profile1.profile_version
        kd_value_1 = profile1.dimensions["knowledge_depth"]["value"]

        # Apply same evidence again
        profile2 = await apply_profile_evidence(db_session, user_id=user_id, evidence=evidence)
        version2 = profile2.profile_version
        kd_value_2 = profile2.dimensions["knowledge_depth"]["value"]

        assert version2 == version1
        assert kd_value_2 == kd_value_1

    async def test_no_duplicate_evidence_records(self, db_session):
        user_id = await _create_user(db_session)

        evidence = [
            ProfileEvidenceInput(
                dimension="knowledge_depth",
                value=0.6,
                confidence=0.8,
                evidence_type="conversation_profile",
                evidence_id="session-1",
            ),
            ProfileEvidenceInput(
                dimension="concept_grasp",
                value=0.7,
                confidence=0.8,
                evidence_type="conversation_profile",
                evidence_id="session-1",
            ),
        ]

        await apply_profile_evidence(db_session, user_id=user_id, evidence=evidence)
        await apply_profile_evidence(db_session, user_id=user_id, evidence=evidence)

        result = await db_session.execute(
            select(StudentProfileEvidence).where(StudentProfileEvidence.user_id == user_id)
        )
        records = list(result.scalars().all())
        assert len(records) == 2  # Not 4

    async def test_different_evidence_id_merges(self, db_session):
        """Different evidence_id should be treated as new evidence."""
        user_id = await _create_user(db_session)

        evidence1 = [
            ProfileEvidenceInput(
                dimension="knowledge_depth",
                value=0.5,
                confidence=0.7,
                evidence_type="conversation_profile",
                evidence_id="session-1",
            ),
        ]
        profile1 = await apply_profile_evidence(db_session, user_id=user_id, evidence=evidence1)
        version1 = profile1.profile_version  # Capture before second call (same object)

        evidence2 = [
            ProfileEvidenceInput(
                dimension="knowledge_depth",
                value=0.7,
                confidence=0.8,
                evidence_type="conversation_profile",
                evidence_id="session-2",
            ),
        ]
        profile2 = await apply_profile_evidence(db_session, user_id=user_id, evidence=evidence2)

        assert profile2.profile_version == version1 + 1
        # Weighted merge should produce a value between 0.5 and 0.7
        kd = profile2.dimensions["knowledge_depth"]["value"]
        assert 0.5 < kd < 0.7

    async def test_different_evidence_type_merges(self, db_session):
        """Same dimension but different evidence_type should be treated as new."""
        user_id = await _create_user(db_session)

        conv_evidence = [
            ProfileEvidenceInput(
                dimension="knowledge_depth",
                value=0.5,
                confidence=0.7,
                evidence_type="conversation_profile",
                evidence_id="source-1",
            ),
        ]
        profile1 = await apply_profile_evidence(db_session, user_id=user_id, evidence=conv_evidence)
        version1 = profile1.profile_version  # Capture before second call (same object)

        assess_evidence = [
            ProfileEvidenceInput(
                dimension="knowledge_depth",
                value=0.8,
                confidence=0.9,
                evidence_type="assessment_attempt",
                evidence_id="source-1",  # Same ID but different type
            ),
        ]
        profile2 = await apply_profile_evidence(db_session, user_id=user_id, evidence=assess_evidence)

        assert profile2.profile_version == version1 + 1


class TestAssessmentEvidenceMerge:
    async def test_assessment_evidence_applies(self, db_session):
        user_id = await _create_user(db_session)

        profile = await apply_assessment_evidence(
            db_session,
            user_id=user_id,
            attempt_id="att-1",
            score=75.0,
            passed=True,
            node_title="Python Basics",
            weak_concepts=["loops", "functions"],
        )

        assert profile.profile_version >= 1
        assert "knowledge_depth" in profile.dimensions
        assert "concept_grasp" in profile.dimensions
        assert "error_pattern" in profile.dimensions

    async def test_assessment_evidence_idempotent(self, db_session):
        user_id = await _create_user(db_session)

        profile1 = await apply_assessment_evidence(
            db_session,
            user_id=user_id,
            attempt_id="att-2",
            score=80.0,
            passed=True,
            node_title="Test",
        )
        version1 = profile1.profile_version

        profile2 = await apply_assessment_evidence(
            db_session,
            user_id=user_id,
            attempt_id="att-2",
            score=80.0,
            passed=True,
            node_title="Test",
        )
        version2 = profile2.profile_version

        assert version2 == version1


class TestDiagnosticEvidenceMerge:
    async def test_diagnostic_evidence_applies(self, db_session):
        user_id = await _create_user(db_session)

        profile = await apply_diagnostic_evidence(
            db_session,
            user_id=user_id,
            attempt_id="diag-1",
            percentage=60.0,
            weak_areas=["variables", "loops"],
        )

        assert profile.profile_version >= 1
        assert "knowledge_depth" in profile.dimensions
        assert "prerequisite_mastery" in profile.dimensions
        assert "error_pattern" in profile.dimensions

    async def test_diagnostic_evidence_idempotent(self, db_session):
        user_id = await _create_user(db_session)

        profile1 = await apply_diagnostic_evidence(
            db_session,
            user_id=user_id,
            attempt_id="diag-2",
            percentage=70.0,
        )
        version1 = profile1.profile_version

        profile2 = await apply_diagnostic_evidence(
            db_session,
            user_id=user_id,
            attempt_id="diag-2",
            percentage=70.0,
        )
        version2 = profile2.profile_version

        assert version2 == version1
