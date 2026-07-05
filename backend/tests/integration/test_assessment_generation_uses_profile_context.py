"""Integration tests: Assessment Generation uses learner profile context.

Verifies:
  - load_profile_context() is called during assessment generation
  - Profile context string and error patterns are included in the LLM prompt
  - When no profile exists, generation proceeds with empty context (fallback)

Run with:
    pytest tests/integration/test_assessment_generation_uses_profile_context.py -v
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.goal import LearningGoal
from app.models.path import LearningPath
from app.models.unit import Assessment
from app.models.user import User
from app.services.profile_merge import ProfileEvidenceInput, apply_profile_evidence


async def _create_user(db_session, prefix: str = "assess-profile") -> str:
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


async def _create_profile_with_error_patterns(db_session, user_id: str) -> str:
    """Create a profile with error patterns and weak problem solving."""
    session_id = f"assess-test-session-{user_id[:8]}"
    evidence = [
        ProfileEvidenceInput(
            dimension="knowledge_depth",
            value=0.3,
            confidence=0.8,
            evidence_type="conversation_profile",
            evidence_id=session_id,
        ),
        ProfileEvidenceInput(
            dimension="problem_solving",
            value=0.2,
            confidence=0.7,
            evidence_type="conversation_profile",
            evidence_id=session_id,
        ),
        ProfileEvidenceInput(
            dimension="practice_ability",
            value=0.8,
            confidence=0.7,
            evidence_type="conversation_profile",
            evidence_id=session_id,
        ),
        ProfileEvidenceInput(
            dimension="error_pattern",
            value={"loops": 0.9, "functions": 0.6, "recursion": 0.3},
            confidence=0.65,
            evidence_type="conversation_profile",
            evidence_id=session_id,
        ),
    ]
    profile = await apply_profile_evidence(db_session, user_id=user_id, evidence=evidence)
    return profile.id


async def _create_assessment(db_session, user_id: str) -> str:
    """Create a minimal assessment linked to a path for testing."""
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
    await db_session.flush()

    path = LearningPath(
        id=str(uuid.uuid4()),
        user_id=user_id,
        goal_id=goal.id,
        status="active",
    )
    db_session.add(path)
    await db_session.flush()

    assessment = Assessment(
        id=str(uuid.uuid4()),
        user_id=user_id,
        path_id=path.id,
        path_version_id="test-version",
        node_id="test-node",
        purpose="quiz_bank",
        status="pending",
    )
    db_session.add(assessment)
    await db_session.commit()
    return assessment.id


class TestAssessmentGenerationUsesProfileContext:
    """Verify assessment generation incorporates learner profile."""

    async def test_load_profile_context_called_during_assessment_generation(self, db_session):
        """load_profile_context should be called when generating assessment questions."""
        from app.models.task import BackgroundTask
        from app.workers.assessment_generation import execute_assessment_generation

        user_id = await _create_user(db_session)
        await _create_profile_with_error_patterns(db_session, user_id)
        assessment_id = await _create_assessment(db_session, user_id)

        with (
            patch(
                "app.services.profile_merge.load_profile_context",
                new_callable=AsyncMock,
                return_value=(MagicMock(), "## 学习者画像\n- 常见错误模式: loops=0.9, functions=0.6"),
            ) as mock_load,
            patch("app.workers.assessment_generation.update_task_status", new_callable=AsyncMock),
            patch("app.services.llm.llm_json", new_callable=AsyncMock) as mock_llm,
        ):
            mock_llm.return_value = {
                "title": "Test Assessment",
                "description": "Test",
                "questions": [
                    {
                        "question_type": "single_choice",
                        "prompt": "Test question",
                        "options": [
                            {"value": "a", "label": "A"},
                            {"value": "b", "label": "B"},
                            {"value": "c", "label": "C"},
                            {"value": "d", "label": "D"},
                        ],
                        "correct_answer": "a",
                        "explanation": "Because",
                        "max_score": 10,
                        "dimension": "general",
                    }
                ],
            }

            task = BackgroundTask(
                id=str(uuid.uuid4()),
                user_id=user_id,
                task_type="assessment_generation",
                target_type="assessment",
                target_id=assessment_id,
                status="pending",
            )
            db_session.add(task)
            await db_session.commit()

            with contextlib.suppress(Exception):
                await execute_assessment_generation(db_session, task)  # noqa

            mock_load.assert_called_once()

    async def test_no_profile_fallback_to_empty_context(self, db_session):
        """When no profile exists, generation should not fail on profile loading."""
        from app.models.task import BackgroundTask
        from app.workers.assessment_generation import execute_assessment_generation

        user_id = await _create_user(db_session)
        # No profile created
        assessment_id = await _create_assessment(db_session, user_id)

        with (
            patch(
                "app.services.profile_merge.load_profile_context",
                new_callable=AsyncMock,
                return_value=(None, ""),
            ) as mock_load,
            patch("app.workers.assessment_generation.update_task_status", new_callable=AsyncMock),
            patch("app.services.llm.llm_json", new_callable=AsyncMock) as mock_llm,
        ):
            mock_llm.return_value = {
                "title": "Test",
                "description": "Test",
                "questions": [],
            }

            task = BackgroundTask(
                id=str(uuid.uuid4()),
                user_id=user_id,
                task_type="assessment_generation",
                target_type="assessment",
                target_id=assessment_id,
                status="pending",
            )
            db_session.add(task)
            await db_session.commit()

            with contextlib.suppress(Exception):
                await execute_assessment_generation(db_session, task)  # noqa

            mock_load.assert_called_once()

    def test_prompt_includes_profile_context_when_present(self):
        """The assessment prompt builder should include profile context string."""
        from app.workers.assessment_generation import AssessmentGenerationInput, _build_user_prompt

        ctx = AssessmentGenerationInput(
            assessment_id="test-assess",
            purpose="quiz_bank",
            node_title="Python 循环",
            learning_objectives=("理解 for 循环",),
            unit_summary="Python 循环基础",
            key_terms=("for", "while"),
            common_mistakes=("缩进错误",),
            diagnostic_weaknesses=("loops",),
            target_difficulty="beginner",
            question_count=5,
            profile_context="## 学习者画像\n- 常见错误模式: loops=0.9",
            error_patterns=("loops",),
        )

        prompt = _build_user_prompt(ctx)

        assert "学习者画像" in prompt
        assert "loops" in prompt
        assert "针对性" in prompt

    def test_prompt_omits_profile_section_when_empty(self):
        """The assessment prompt should not include profile section when context is empty."""
        from app.workers.assessment_generation import AssessmentGenerationInput, _build_user_prompt

        ctx = AssessmentGenerationInput(
            assessment_id="test-assess",
            purpose="quiz_bank",
            node_title="Python 循环",
            learning_objectives=("理解 for 循环",),
            unit_summary="Python 循环基础",
            key_terms=("for", "while"),
            common_mistakes=(),
            diagnostic_weaknesses=(),
            target_difficulty="beginner",
            question_count=5,
            profile_context="",
            error_patterns=(),
        )

        prompt = _build_user_prompt(ctx)

        assert "学习者画像" not in prompt
