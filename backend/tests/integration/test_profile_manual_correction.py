"""Integration tests for profile manual correction.

Verifies:
  - Manual correction creates StudentProfile if it doesn't exist
  - Manual correction updates the specified dimension
  - Manual correction writes evidence_type=manual_correction
  - Manual correction increases profile_version
  - Manual correction accepts dict values for error_pattern
  - Manual correction accepts list values for resource_preference

Run with:
    pytest tests/integration/test_profile_manual_correction.py -v
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.models.profile import StudentProfile
from app.models.user import StudentProfileEvidence, User
from app.services.profile_merge import ProfileEvidenceInput, apply_profile_evidence


async def _create_user(db_session, prefix: str = "profile-mc") -> str:
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


async def _create_profile_with_evidence(db_session, user_id: str) -> StudentProfile:
    """Create a profile with initial conversation evidence."""
    evidence = [
        ProfileEvidenceInput(
            dimension="knowledge_depth",
            value=0.5,
            confidence=0.7,
            evidence_type="conversation_profile",
            evidence_id="initial-session",
        ),
        ProfileEvidenceInput(
            dimension="concept_grasp",
            value=0.6,
            confidence=0.7,
            evidence_type="conversation_profile",
            evidence_id="initial-session",
        ),
    ]
    return await apply_profile_evidence(db_session, user_id=user_id, evidence=evidence)


class TestManualCorrectionViaService:
    """Test manual correction through the profile_merge service."""

    async def test_manual_correction_updates_dimension(self, db_session):
        user_id = await _create_user(db_session)
        profile = await _create_profile_with_evidence(db_session, user_id)
        version_before = profile.profile_version

        # Apply manual correction
        evidence = [
            ProfileEvidenceInput(
                dimension="knowledge_depth",
                value=0.9,
                confidence=1.0,
                evidence_type="manual_correction",
                evidence_id=str(uuid.uuid4()),
                evidence_text="User corrected their knowledge depth",
            ),
        ]
        updated = await apply_profile_evidence(db_session, user_id=user_id, evidence=evidence)

        assert updated.profile_version == version_before + 1
        # Weighted merge of old (0.5, conf 0.7) and new (0.9, conf 1.0)
        # = (0.5*0.7 + 0.9*1.0) / (0.7+1.0) ≈ 0.735
        kd_value = updated.dimensions["knowledge_depth"]["value"]
        assert 0.5 < kd_value <= 0.9
        assert updated.dimensions["knowledge_depth"]["source"] == "manual_correction"

    async def test_manual_correction_writes_evidence(self, db_session):
        user_id = await _create_user(db_session)
        await _create_profile_with_evidence(db_session, user_id)

        correction_id = str(uuid.uuid4())
        evidence = [
            ProfileEvidenceInput(
                dimension="learning_pace",
                value="fast",
                confidence=1.0,
                evidence_type="manual_correction",
                evidence_id=correction_id,
                evidence_text="User corrected pace",
            ),
        ]
        await apply_profile_evidence(db_session, user_id=user_id, evidence=evidence)

        result = await db_session.execute(
            select(StudentProfileEvidence).where(
                StudentProfileEvidence.user_id == user_id,
                StudentProfileEvidence.evidence_type == "manual_correction",
            )
        )
        records = list(result.scalars().all())
        assert len(records) == 1
        assert records[0].dimension == "learning_pace"
        assert records[0].evidence_id == correction_id

    async def test_manual_correction_accepts_dict_error_pattern(self, db_session):
        user_id = await _create_user(db_session)
        await _create_profile_with_evidence(db_session, user_id)

        error_dict = {"loops": 0.8, "recursion": 0.6}
        evidence = [
            ProfileEvidenceInput(
                dimension="error_pattern",
                value=error_dict,
                confidence=1.0,
                evidence_type="manual_correction",
                evidence_id=str(uuid.uuid4()),
            ),
        ]
        updated = await apply_profile_evidence(db_session, user_id=user_id, evidence=evidence)

        dim = updated.dimensions.get("error_pattern")
        assert dim is not None
        assert isinstance(dim["value"], dict)
        assert "loops" in dim["value"]

    async def test_manual_correction_accepts_list_preference(self, db_session):
        user_id = await _create_user(db_session)
        await _create_profile_with_evidence(db_session, user_id)

        evidence = [
            ProfileEvidenceInput(
                dimension="resource_preference",
                value=["video", "project", "quiz"],
                confidence=1.0,
                evidence_type="manual_correction",
                evidence_id=str(uuid.uuid4()),
            ),
        ]
        updated = await apply_profile_evidence(db_session, user_id=user_id, evidence=evidence)

        dim = updated.dimensions.get("resource_preference")
        assert dim is not None
        assert isinstance(dim["value"], list)
        assert "video" in dim["value"]

    async def test_manual_correction_creates_profile_if_missing(self, db_session):
        """Manual correction should create a profile if none exists."""
        user_id = await _create_user(db_session)

        # No profile exists yet
        result = await db_session.execute(select(StudentProfile).where(StudentProfile.user_id == user_id))
        assert result.scalar_one_or_none() is None

        evidence = [
            ProfileEvidenceInput(
                dimension="knowledge_depth",
                value=0.7,
                confidence=1.0,
                evidence_type="manual_correction",
                evidence_id=str(uuid.uuid4()),
            ),
        ]
        profile = await apply_profile_evidence(db_session, user_id=user_id, evidence=evidence)

        assert profile is not None
        assert profile.user_id == user_id
        assert profile.profile_version == 1
