"""Integration tests for profile personalization context.

Verifies:
  - load_profile_context() returns (profile, context_string) for existing profiles
  - load_profile_context() returns (None, "") when no profile exists
  - load_profile_context() returns (None, "") when profile has empty dimensions
  - Context string contains structured dimension data
  - Context string does NOT contain internal prompt / CoT / raw LLM response

Run with:
    pytest tests/integration/test_profile_personalization_context.py -v
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.models.user import User
from app.services.profile_merge import (
    ProfileEvidenceInput,
    apply_profile_evidence,
    load_profile_context,
)


async def _create_user(db_session, prefix: str = "profile-ctx") -> str:
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


async def _create_profile_with_dimensions(db_session, user_id: str) -> str:
    """Create a profile with all 8 dimensions populated."""
    evidence = [
        ProfileEvidenceInput(
            dimension="knowledge_depth",
            value=0.4,
            confidence=0.8,
            evidence_type="conversation_profile",
            evidence_id="ctx-session",
        ),
        ProfileEvidenceInput(
            dimension="prerequisite_mastery",
            value=0.3,
            confidence=0.7,
            evidence_type="conversation_profile",
            evidence_id="ctx-session",
        ),
        ProfileEvidenceInput(
            dimension="concept_grasp",
            value=0.5,
            confidence=0.7,
            evidence_type="conversation_profile",
            evidence_id="ctx-session",
        ),
        ProfileEvidenceInput(
            dimension="problem_solving",
            value=0.4,
            confidence=0.6,
            evidence_type="conversation_profile",
            evidence_id="ctx-session",
        ),
        ProfileEvidenceInput(
            dimension="practice_ability",
            value=0.3,
            confidence=0.6,
            evidence_type="conversation_profile",
            evidence_id="ctx-session",
        ),
        ProfileEvidenceInput(
            dimension="learning_pace",
            value="slow",
            confidence=0.7,
            evidence_type="conversation_profile",
            evidence_id="ctx-session",
        ),
        ProfileEvidenceInput(
            dimension="resource_preference",
            value=["video", "project"],
            confidence=0.7,
            evidence_type="conversation_profile",
            evidence_id="ctx-session",
        ),
        ProfileEvidenceInput(
            dimension="error_pattern",
            value={"loops": 0.8, "functions": 0.6},
            confidence=0.65,
            evidence_type="conversation_profile",
            evidence_id="ctx-session",
        ),
    ]
    profile = await apply_profile_evidence(db_session, user_id=user_id, evidence=evidence)
    return profile.id


class TestLoadProfileContext:
    async def test_returns_none_when_no_profile(self, db_session):
        user_id = await _create_user(db_session)

        profile, context = await load_profile_context(db_session, user_id)

        assert profile is None
        assert context == ""

    async def test_returns_profile_and_context(self, db_session):
        user_id = await _create_user(db_session)
        await _create_profile_with_dimensions(db_session, user_id)

        profile, context = await load_profile_context(db_session, user_id)

        assert profile is not None
        assert profile.user_id == user_id
        assert len(context) > 0

    async def test_context_contains_dimension_labels(self, db_session):
        user_id = await _create_user(db_session)
        await _create_profile_with_dimensions(db_session, user_id)

        _, context = await load_profile_context(db_session, user_id)

        # Should contain human-readable dimension labels
        assert "知识深度" in context
        assert "先修知识掌握" in context
        assert "概念理解能力" in context
        assert "学习节奏" in context
        assert "资源偏好" in context
        assert "常见错误模式" in context

    async def test_context_contains_header(self, db_session):
        user_id = await _create_user(db_session)
        await _create_profile_with_dimensions(db_session, user_id)

        _, context = await load_profile_context(db_session, user_id)

        assert "学习者画像" in context

    async def test_context_does_not_contain_internal_fields(self, db_session):
        """Context should NOT contain internal prompt / CoT / raw LLM response."""
        user_id = await _create_user(db_session)
        await _create_profile_with_dimensions(db_session, user_id)

        _, context = await load_profile_context(db_session, user_id)

        forbidden = ["internal_prompt", "raw_llm_response", "model_config", "chain_of_thought", "system_prompt"]
        for word in forbidden:
            assert word not in context.lower(), f"Context should not contain '{word}'"

    async def test_context_contains_numeric_values(self, db_session):
        user_id = await _create_user(db_session)
        await _create_profile_with_dimensions(db_session, user_id)

        _, context = await load_profile_context(db_session, user_id)

        # Should contain confidence percentages
        assert "置信度" in context

    async def test_context_contains_list_values(self, db_session):
        user_id = await _create_user(db_session)
        await _create_profile_with_dimensions(db_session, user_id)

        _, context = await load_profile_context(db_session, user_id)

        # resource_preference is ["video", "project"]
        assert "video" in context or "project" in context

    async def test_context_contains_dict_values(self, db_session):
        user_id = await _create_user(db_session)
        await _create_profile_with_dimensions(db_session, user_id)

        _, context = await load_profile_context(db_session, user_id)

        # error_pattern is {"loops": 0.8, "functions": 0.6}
        assert "loops" in context

    async def test_empty_dimensions_returns_empty_context(self, db_session):
        """Profile with empty dimensions should return empty context."""
        user_id = await _create_user(db_session)

        # Create a profile manually with empty dimensions
        from app.models.profile import StudentProfile

        profile = StudentProfile(
            id=str(uuid.uuid4()),
            user_id=user_id,
            status="active",
            profile_version=1,
            dimensions={},
            confidence=0.0,
        )
        db_session.add(profile)
        await db_session.commit()

        result_profile, context = await load_profile_context(db_session, user_id)

        assert result_profile is None
        assert context == ""
