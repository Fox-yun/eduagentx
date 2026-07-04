"""Integration tests for profile conversation lifecycle.

Verifies:
  - create_session persists learning_goal_text and target_context
  - create_session generates initial assistant message
  - process_message increments turn_count
  - process_message updates extracted_dimensions
  - process_message generates assistant response
  - Fallback extraction works when LLM is unavailable

All LLM calls are mocked to trigger fallback extraction, ensuring
tests run fast and deterministic without external API dependencies.

Run with:
    pytest tests/integration/test_profile_conversation.py -v
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models.profile import ProfileConversationSession
from app.models.user import User
from app.services.llm import LLMError
from app.services.profile_conversation import ProfileConversationService


async def _create_user(db_session, prefix: str = "profile-conv") -> str:
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


@pytest.fixture(autouse=True)
def _mock_llm_failure():
    """Mock llm_json to raise LLMError, triggering fallback extraction."""
    with patch(
        "app.services.profile_conversation.llm_json",
        new_callable=AsyncMock,
        side_effect=LLMError("LLM disabled in test"),
    ):
        yield


class TestCreateSession:
    async def test_session_persists_learning_goal_text(self, db_session):
        """E0-A1: learning_goal_text is persisted on the session row."""
        user_id = await _create_user(db_session)
        svc = ProfileConversationService(db_session)

        session = await svc.create_session(
            user_id=user_id,
            learning_goal="我想在两个月内掌握 Python 网络爬虫",
            target_context="在职转行，每天可用 2 小时",
        )

        # Re-fetch to verify persistence
        result = await db_session.execute(
            select(ProfileConversationSession).where(ProfileConversationSession.id == session.id)
        )
        fresh = result.scalar_one()
        assert fresh.learning_goal_text == "我想在两个月内掌握 Python 网络爬虫"
        assert fresh.target_context == "在职转行，每天可用 2 小时"

    async def test_session_initial_status_active(self, db_session):
        user_id = await _create_user(db_session)
        svc = ProfileConversationService(db_session)

        session = await svc.create_session(
            user_id=user_id,
            learning_goal="学 Python",
        )

        assert session.status == "active"
        assert session.turn_count == 0
        assert session.extracted_dimensions == {}

    async def test_session_creates_initial_assistant_message(self, db_session):
        user_id = await _create_user(db_session)
        svc = ProfileConversationService(db_session)

        session = await svc.create_session(
            user_id=user_id,
            learning_goal="学 Python 数据分析",
        )

        messages = await svc.get_messages(session.id)
        assert len(messages) >= 1
        assert messages[0].role == "assistant"
        assert len(messages[0].content) > 0

    async def test_get_session_returns_none_for_wrong_user(self, db_session):
        user_id = await _create_user(db_session)
        other_user_id = await _create_user(db_session, prefix="other")
        svc = ProfileConversationService(db_session)

        session = await svc.create_session(
            user_id=user_id,
            learning_goal="学 Python",
        )

        # Wrong user should not find the session
        result = await svc.get_session(session.id, other_user_id)
        assert result is None


class TestProcessMessage:
    async def test_turn_count_increments(self, db_session):
        user_id = await _create_user(db_session)
        svc = ProfileConversationService(db_session)

        session = await svc.create_session(
            user_id=user_id,
            learning_goal="学 Python 网络爬虫",
        )

        # LLM is mocked to fail → fallback extraction is used
        await svc.process_message(session, "我基础比较薄弱，没学过编程")

        # Re-fetch session
        fresh = await svc.get_session(session.id, user_id)
        assert fresh is not None
        assert fresh.turn_count == 1

    async def test_extracted_dimensions_updated(self, db_session):
        user_id = await _create_user(db_session)
        svc = ProfileConversationService(db_session)

        session = await svc.create_session(
            user_id=user_id,
            learning_goal="学 Python 网络爬虫",
        )

        await svc.process_message(session, "我零基础，没学过编程，每天可以学习 2 小时，喜欢看视频")

        # Re-fetch session
        fresh = await svc.get_session(session.id, user_id)
        assert fresh is not None
        # Fallback extraction should have captured some dimensions
        assert len(fresh.extracted_dimensions) > 0

    async def test_assistant_message_saved(self, db_session):
        user_id = await _create_user(db_session)
        svc = ProfileConversationService(db_session)

        session = await svc.create_session(
            user_id=user_id,
            learning_goal="学 Python",
        )

        await svc.process_message(session, "我基础薄弱")

        messages = await svc.get_messages(session.id)
        # Should have: initial assistant + user + assistant response
        assert len(messages) >= 3
        roles = [m.role for m in messages]
        assert "user" in roles
        assert roles.count("assistant") >= 2

    async def test_result_contains_required_keys(self, db_session):
        user_id = await _create_user(db_session)
        svc = ProfileConversationService(db_session)

        session = await svc.create_session(
            user_id=user_id,
            learning_goal="学 Python",
        )

        result = await svc.process_message(session, "我基础薄弱")

        assert "assistant_message" in result
        assert "extracted_dimensions" in result
        assert "missing_dimensions" in result
        assert "ready_to_finalize" in result
        assert isinstance(result["assistant_message"], str)
        assert isinstance(result["ready_to_finalize"], bool)

    async def test_multiple_turns_accumulate_dimensions(self, db_session):
        user_id = await _create_user(db_session)
        svc = ProfileConversationService(db_session)

        session = await svc.create_session(
            user_id=user_id,
            learning_goal="学 Python 网络爬虫",
        )

        # Turn 1: knowledge depth
        await svc.process_message(session, "我零基础，完全没学过编程")
        fresh = await svc.get_session(session.id, user_id)
        assert fresh is not None
        dims_after_1 = len(fresh.extracted_dimensions)

        # Turn 2: learning pace + resource preference
        await svc.process_message(session, "每天可以学 2 小时，喜欢看视频和做项目")
        fresh = await svc.get_session(session.id, user_id)
        assert fresh is not None
        dims_after_2 = len(fresh.extracted_dimensions)
        assert dims_after_2 >= dims_after_1
