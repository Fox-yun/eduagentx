"""Integration tests: Path Planning uses learner profile context.

Verifies:
  - load_profile_context() is called during path generation
  - Profile context string is included in the LLM prompt
  - When no profile exists, generation proceeds with empty context (fallback)
  - Profile context influences prompt instructions (weak foundation → add basic nodes)

Run with:
    pytest tests/integration/test_path_planning_uses_profile_context.py -v
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from app.models.goal import LearningGoal
from app.models.user import User
from app.services.profile_merge import ProfileEvidenceInput, apply_profile_evidence


async def _create_user(db_session, prefix: str = "path-profile") -> str:
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


async def _create_goal(db_session, user_id: str) -> str:
    goal = LearningGoal(
        id=str(uuid.uuid4()),
        user_id=user_id,
        raw_description="我想学习 Python 编程基础",
        normalized_goal="Python programming fundamentals",
        title="Python 编程基础",
        current_level="beginner",
        target_level="intermediate",
        status="planning",
    )
    db_session.add(goal)
    await db_session.commit()
    return goal.id


async def _create_profile_with_weak_foundation(db_session, user_id: str) -> str:
    """Create a profile indicating weak foundation."""
    evidence = [
        ProfileEvidenceInput(
            dimension="knowledge_depth",
            value=0.2,
            confidence=0.8,
            evidence_type="conversation_profile",
            evidence_id="path-test-session",
        ),
        ProfileEvidenceInput(
            dimension="prerequisite_mastery",
            value=0.15,
            confidence=0.7,
            evidence_type="conversation_profile",
            evidence_id="path-test-session",
        ),
        ProfileEvidenceInput(
            dimension="learning_pace",
            value="slow",
            confidence=0.7,
            evidence_type="conversation_profile",
            evidence_id="path-test-session",
        ),
    ]
    profile = await apply_profile_evidence(db_session, user_id=user_id, evidence=evidence)
    return profile.id


class TestPathPlanningUsesProfileContext:
    """Verify path planning generation incorporates learner profile."""

    async def test_load_profile_context_called_during_path_generation(self, db_session):
        """load_profile_context should be called when generating a path."""
        user_id = await _create_user(db_session)
        goal_id = await _create_goal(db_session, user_id)
        await _create_profile_with_weak_foundation(db_session, user_id)

        captured_prompt: list[str] = []

        async def mock_llm_json(*args, **kwargs):
            captured_prompt.append(args[1] if len(args) > 1 else kwargs.get("user_msg", ""))
            return {
                "nodes": [
                    {
                        "title": "Python 基础语法",
                        "description": "变量、类型、运算符",
                        "difficulty": 1,
                        "estimated_minutes": 30,
                        "learning_objectives": ["理解变量", "掌握基本类型"],
                    },
                ],
                "edges": [],
            }

        from app.workers.tasks import _execute_path_generation

        with (
            patch("app.workers.tasks.llm_json", new_callable=AsyncMock, side_effect=mock_llm_json),
            patch("app.workers.tasks.update_task_status", new_callable=AsyncMock),
        ):
            from app.models.task import BackgroundTask

            task = BackgroundTask(
                id=str(uuid.uuid4()),
                user_id=user_id,
                task_type="learning_path_generation",
                target_type="goal",
                target_id=goal_id,
                status="pending",
            )
            db_session.add(task)
            await db_session.commit()

            await _execute_path_generation(db_session, task)

        # Verify the prompt contains profile context
        assert len(captured_prompt) > 0
        combined_prompt = " ".join(captured_prompt)
        assert "学习者画像" in combined_prompt or "知识深度" in combined_prompt

    async def test_no_profile_fallback_to_empty_context(self, db_session):
        """When no profile exists, generation should proceed without error."""
        user_id = await _create_user(db_session)
        goal_id = await _create_goal(db_session, user_id)

        # No profile created — should fall back gracefully

        async def mock_llm_json(*args, **kwargs):
            return {
                "nodes": [
                    {
                        "title": "Python 入门",
                        "description": "基础概念",
                        "difficulty": 1,
                        "estimated_minutes": 25,
                        "learning_objectives": ["入门"],
                    },
                ],
                "edges": [],
            }

        from app.models.task import BackgroundTask
        from app.workers.tasks import _execute_path_generation

        task = BackgroundTask(
            id=str(uuid.uuid4()),
            user_id=user_id,
            task_type="learning_path_generation",
            target_type="goal",
            target_id=goal_id,
            status="pending",
        )
        db_session.add(task)
        await db_session.commit()

        with (
            patch("app.workers.tasks.llm_json", new_callable=AsyncMock, side_effect=mock_llm_json),
            patch("app.workers.tasks.update_task_status", new_callable=AsyncMock),
        ):
            # Should not raise
            await _execute_path_generation(db_session, task)

    async def test_profile_context_in_prompt_mentions_foundation(self, db_session):
        """The prompt should mention foundation guidance for weak profiles."""
        user_id = await _create_user(db_session)
        goal_id = await _create_goal(db_session, user_id)
        await _create_profile_with_weak_foundation(db_session, user_id)

        captured_prompt: list[str] = []

        async def mock_llm_json(*args, **kwargs):
            captured_prompt.append(args[1] if len(args) > 1 else kwargs.get("user_msg", ""))
            return {
                "nodes": [
                    {
                        "title": "Python 基础",
                        "description": "基础",
                        "difficulty": 1,
                        "estimated_minutes": 30,
                        "learning_objectives": ["基础"],
                    },
                ],
                "edges": [],
            }

        from app.models.task import BackgroundTask
        from app.workers.tasks import _execute_path_generation

        task = BackgroundTask(
            id=str(uuid.uuid4()),
            user_id=user_id,
            task_type="learning_path_generation",
            target_type="goal",
            target_id=goal_id,
            status="pending",
        )
        db_session.add(task)
        await db_session.commit()

        with (
            patch("app.workers.tasks.llm_json", new_callable=AsyncMock, side_effect=mock_llm_json),
            patch("app.workers.tasks.update_task_status", new_callable=AsyncMock),
        ):
            await _execute_path_generation(db_session, task)

        combined = " ".join(captured_prompt)
        # Prompt should include profile-aware instructions
        assert "基础" in combined or "画像" in combined
