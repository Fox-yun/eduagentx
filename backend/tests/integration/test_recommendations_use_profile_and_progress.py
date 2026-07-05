"""Integration tests: Recommendations use learner profile and learning progress.

Verifies:
  - RecommendationService loads StudentProfile for personalised reasons
  - Recommendation reasons reference profile dimensions (learning_pace, knowledge_depth)
  - Review recommendations reference error_pattern and concept_grasp
  - Practice recommendations reference practice_ability and resource_preference
  - Resource recommendations reference resource_preference
  - When no profile exists, recommendations still work (fallback to generic reasons)

Run with:
    pytest tests/integration/test_recommendations_use_profile_and_progress.py -v
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.models.goal import LearningGoal
from app.models.path import LearningNode, LearningPath, LearningPathVersion
from app.models.progress import LearningProgress
from app.models.user import User
from app.services.profile_merge import ProfileEvidenceInput, apply_profile_evidence
from app.services.recommendations import RecommendationService


async def _create_user(db_session, prefix: str = "rec-profile") -> str:
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


async def _create_path_with_nodes(
    db_session, user_id: str, goal_id: str
) -> tuple[str, list[str]]:
    """Create a learning path with version and nodes. Returns (path_id, node_ids)."""
    path_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())

    path = LearningPath(
        id=path_id,
        user_id=user_id,
        goal_id=goal_id,
        title="Test Path",
        status="active",
        active_version_id=version_id,
    )
    db_session.add(path)

    version = LearningPathVersion(
        id=version_id,
        path_id=path_id,
        version_number=1,
        status="active",
        created_by="system",
    )
    db_session.add(version)

    node_ids: list[str] = []
    for i in range(3):
        node_id = str(uuid.uuid4())
        node = LearningNode(
            id=node_id,
            version_id=version_id,
            title=f"Node {i + 1}",
            description=f"Description {i + 1}",
            node_order=i,
            difficulty="beginner" if i == 0 else "intermediate",
            estimated_minutes=30,
            status="available",
            mastery=0.0,
        )
        db_session.add(node)
        node_ids.append(node_id)

    await db_session.commit()
    return path_id, node_ids


async def _create_goal(db_session, user_id: str) -> str:
    goal = LearningGoal(
        id=str(uuid.uuid4()),
        user_id=user_id,
        raw_description="学习 Python",
        normalized_goal="Python",
        title="Python 基础",
        current_level="beginner",
        target_level="intermediate",
        status="planning",
    )
    db_session.add(goal)
    await db_session.commit()
    return goal.id


async def _create_profile(db_session, user_id: str) -> str:
    """Create a profile with meaningful dimensions for recommendation testing."""
    evidence = [
        ProfileEvidenceInput(
            dimension="knowledge_depth",
            value=0.2,
            confidence=0.8,
            evidence_type="conversation_profile",
            evidence_id="rec-test-session",
        ),
        ProfileEvidenceInput(
            dimension="concept_grasp",
            value=0.3,
            confidence=0.7,
            evidence_type="conversation_profile",
            evidence_id="rec-test-session",
        ),
        ProfileEvidenceInput(
            dimension="practice_ability",
            value=0.25,
            confidence=0.6,
            evidence_type="conversation_profile",
            evidence_id="rec-test-session",
        ),
        ProfileEvidenceInput(
            dimension="learning_pace",
            value="slow",
            confidence=0.7,
            evidence_type="conversation_profile",
            evidence_id="rec-test-session",
        ),
        ProfileEvidenceInput(
            dimension="resource_preference",
            value=["quiz", "reading"],
            confidence=0.7,
            evidence_type="conversation_profile",
            evidence_id="rec-test-session",
        ),
        ProfileEvidenceInput(
            dimension="error_pattern",
            value={"loops": 0.8, "functions": 0.6},
            confidence=0.65,
            evidence_type="conversation_profile",
            evidence_id="rec-test-session",
        ),
    ]
    profile = await apply_profile_evidence(db_session, user_id=user_id, evidence=evidence)
    return profile.id


async def _create_progress(
    db_session, user_id: str, path_id: str, node_id: str, status: str, mastery: float
) -> None:
    progress = LearningProgress(
        id=str(uuid.uuid4()),
        user_id=user_id,
        path_id=path_id,
        node_id=node_id,
        status=status,
        mastery=mastery,
    )
    db_session.add(progress)
    await db_session.commit()


class TestRecommendationsUseProfileAndProgress:
    """Verify recommendation service uses learner profile and progress."""

    async def test_recommendations_with_profile_contain_personalised_reasons(self, db_session):
        """Recommendation reasons should reference profile dimensions."""
        user_id = await _create_user(db_session)
        goal_id = await _create_goal(db_session, user_id)
        path_id, node_ids = await _create_path_with_nodes(db_session, user_id, goal_id)
        await _create_profile(db_session, user_id)

        service = RecommendationService(db_session)
        recommendations = await service.get_recommendations(path_id, user_id)

        assert len(recommendations) > 0

        # At least one recommendation should mention profile-based info
        all_reasons = " ".join(r.get("reason", "") for r in recommendations)
        # Profile-derived keywords should appear in at least some reasons
        profile_keywords = ["学习节奏", "知识基础", "概念理解", "动手实践", "常见薄弱点", "偏好"]
        assert any(kw in all_reasons for kw in profile_keywords), (
            f"Expected at least one profile keyword in reasons, got: {all_reasons}"
        )

    async def test_recommendations_without_profile_still_work(self, db_session):
        """When no profile exists, recommendations should still be generated."""
        user_id = await _create_user(db_session)
        goal_id = await _create_goal(db_session, user_id)
        path_id, node_ids = await _create_path_with_nodes(db_session, user_id, goal_id)
        # No profile created

        service = RecommendationService(db_session)
        recommendations = await service.get_recommendations(path_id, user_id)

        assert len(recommendations) > 0
        # Should still have continue recommendation
        continue_recs = [r for r in recommendations if r["type"] == "continue"]
        assert len(continue_recs) > 0

    async def test_review_recommendation_references_error_pattern(self, db_session):
        """Review recommendations should mention error patterns from profile."""
        user_id = await _create_user(db_session)
        goal_id = await _create_goal(db_session, user_id)
        path_id, node_ids = await _create_path_with_nodes(db_session, user_id, goal_id)
        await _create_profile(db_session, user_id)

        # Mark a node as completed with low mastery to trigger review
        await _create_progress(db_session, user_id, path_id, node_ids[0], "completed", 40.0)

        service = RecommendationService(db_session)
        recommendations = await service.get_recommendations(path_id, user_id)

        review_recs = [r for r in recommendations if r["type"] == "review"]
        assert len(review_recs) > 0

        review_reasons = " ".join(r.get("reason", "") for r in review_recs)
        # Error patterns from profile are "loops" and "functions"
        # The reason should mention concept_grasp or error patterns
        assert "概念" in review_reasons or "薄弱" in review_reasons

    async def test_practice_recommendation_references_practice_ability(self, db_session):
        """Practice recommendations should reference practice_ability from profile."""
        user_id = await _create_user(db_session)
        goal_id = await _create_goal(db_session, user_id)
        path_id, node_ids = await _create_path_with_nodes(db_session, user_id, goal_id)
        await _create_profile(db_session, user_id)

        service = RecommendationService(db_session)
        recommendations = await service.get_recommendations(path_id, user_id)

        practice_recs = [r for r in recommendations if r["type"] == "practice"]
        assert len(practice_recs) > 0

        practice_reasons = " ".join(r.get("reason", "") for r in practice_recs)
        # practice_ability is 0.25 (< 0.4), so should mention practice
        assert "实践" in practice_reasons or "练习" in practice_reasons

    async def test_continue_recommendation_references_learning_pace(self, db_session):
        """Continue recommendation should reference learning_pace from profile."""
        user_id = await _create_user(db_session)
        goal_id = await _create_goal(db_session, user_id)
        path_id, node_ids = await _create_path_with_nodes(db_session, user_id, goal_id)
        await _create_profile(db_session, user_id)

        service = RecommendationService(db_session)
        recommendations = await service.get_recommendations(path_id, user_id)

        continue_recs = [r for r in recommendations if r["type"] == "continue"]
        assert len(continue_recs) > 0

        continue_reason = continue_recs[0].get("reason", "")
        # learning_pace is "slow"
        assert "学习节奏" in continue_reason or "稳扎稳打" in continue_reason

    async def test_recommendation_does_not_leak_internal_prompt(self, db_session):
        """Recommendation reasons should not contain internal prompt/CoT/LLM artifacts."""
        user_id = await _create_user(db_session)
        goal_id = await _create_goal(db_session, user_id)
        path_id, node_ids = await _create_path_with_nodes(db_session, user_id, goal_id)
        await _create_profile(db_session, user_id)

        service = RecommendationService(db_session)
        recommendations = await service.get_recommendations(path_id, user_id)

        forbidden = ["internal_prompt", "raw_llm_response", "chain_of_thought", "system_prompt", "model_config"]
        for rec in recommendations:
            reason = rec.get("reason", "").lower()
            for word in forbidden:
                assert word not in reason, f"Reason should not contain '{word}': {reason}"
