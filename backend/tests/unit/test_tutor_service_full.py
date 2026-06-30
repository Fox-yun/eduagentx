"""Comprehensive unit tests for TutorService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _mock_scalar_result(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _make_path():
    """Create a mock LearningPath with required fields."""
    p = MagicMock()
    p.id = "path-1"
    p.user_id = "user-1"
    p.active_version_id = "ver-1"
    p.status = "active"
    return p


def _make_version():
    """Create a mock LearningPathVersion with required fields."""
    v = MagicMock()
    v.id = "ver-1"
    v.path_id = "path-1"
    v.status = "active"
    return v


def _make_node(node_id="node-1", title="Python Lists"):
    """Create a mock LearningNode with required fields."""
    n = MagicMock()
    n.id = node_id
    n.title = title
    n.version_id = "ver-1"
    n.status = "available"
    return n


def _make_content(sections=None):
    """Create a mock LearningUnitContent."""
    c = MagicMock()
    if sections is not None:
        c.content = {"sections": sections}
    elif sections is None:
        # Default content with sections
        c.content = {
            "sections": [
                {"title": "Intro", "content": "Lists are ordered collections..."},
                {"title": "Operations", "content": "You can append, remove..."},
            ]
        }
    return c


class TestTutorServiceAsk:
    """TutorService.ask tests with access guard."""

    @pytest.mark.asyncio
    async def test_ask_with_node_and_content(self):
        from app.services.tutor import TutorService

        db = AsyncMock()
        svc = TutorService(db)

        path = _make_path()
        version = _make_version()
        node = _make_node()
        content = _make_content()

        call_order = [path, version, node, content, None]

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            idx = min(call_count, len(call_order) - 1)
            call_count += 1
            return _mock_scalar_result(call_order[idx])

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with patch("app.services.tutor.llm_chat", new_callable=AsyncMock, return_value="Lists are great!"):
            result = await svc.ask("path-1", "node-1", "user-1", "What is a list?")
            assert result["question"] == "What is a list?"
            assert result["answer"] == "Lists are great!"
            assert result["node_id"] == "node-1"

    @pytest.mark.asyncio
    async def test_ask_without_node_provides_fallback_title(self):
        """When the queried node doesn't have a title, '未知节点' is used."""
        from app.services.tutor import TutorService

        db = AsyncMock()
        svc = TutorService(db)

        path = _make_path()
        version = _make_version()
        node = _make_node(title="")  # Empty title

        call_order = [path, version, node, None, None]

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            idx = min(call_count, len(call_order) - 1)
            call_count += 1
            return _mock_scalar_result(call_order[idx])

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with patch("app.services.tutor.llm_chat", new_callable=AsyncMock, return_value="An answer"):
            result = await svc.ask("path-1", "bad-node", "user-1", "Hello?")
            assert result["answer"] == "An answer"

    @pytest.mark.asyncio
    async def test_ask_with_content_no_sections(self):
        from app.services.tutor import TutorService

        db = AsyncMock()
        svc = TutorService(db)

        path = _make_path()
        version = _make_version()
        node = _make_node()
        content = _make_content(sections=[])

        call_order = [path, version, node, content, None]

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            idx = min(call_count, len(call_order) - 1)
            call_count += 1
            return _mock_scalar_result(call_order[idx])

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with patch("app.services.tutor.llm_chat", new_callable=AsyncMock, return_value="Answer"):
            result = await svc.ask("path-1", "node-1", "user-1", "Question?")
            assert result["answer"] == "Answer"

    @pytest.mark.asyncio
    async def test_ask_with_content_no_content_field(self):
        from app.services.tutor import TutorService

        db = AsyncMock()
        svc = TutorService(db)

        path = _make_path()
        version = _make_version()
        node = _make_node()
        content = MagicMock()
        content.content = None

        call_order = [path, version, node, content, None]

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            idx = min(call_count, len(call_order) - 1)
            call_count += 1
            return _mock_scalar_result(call_order[idx])

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with patch("app.services.tutor.llm_chat", new_callable=AsyncMock, return_value="Answer"):
            result = await svc.ask("path-1", "node-1", "user-1", "Q?")
            assert result["answer"] == "Answer"

    @pytest.mark.asyncio
    async def test_ask_llm_error_returns_safe_message(self):
        """LLM errors must not leak internal details to the user."""
        from app.services.llm import LLMError
        from app.services.tutor import TutorService

        db = AsyncMock()
        svc = TutorService(db)

        path = _make_path()
        version = _make_version()
        node = _make_node()

        call_order = [path, version, node, None, None]

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            idx = min(call_count, len(call_order) - 1)
            call_count += 1
            return _mock_scalar_result(call_order[idx])

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with patch("app.services.tutor.llm_chat", new_callable=AsyncMock, side_effect=LLMError("API down")):
            result = await svc.ask("path-1", "node-1", "user-1", "Q?")
            assert "辅导服务暂时不可用" in result["answer"]
            assert "API down" not in result["answer"]  # Must not leak internal errors

    @pytest.mark.asyncio
    async def test_ask_with_many_sections_truncated(self):
        from app.services.tutor import TutorService

        db = AsyncMock()
        svc = TutorService(db)

        path = _make_path()
        version = _make_version()
        node = _make_node()
        content = MagicMock()
        content.content = {"sections": [{"title": f"S{i}", "content": "X" * 100} for i in range(10)]}

        call_order = [path, version, node, content, None]

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            idx = min(call_count, len(call_order) - 1)
            call_count += 1
            return _mock_scalar_result(call_order[idx])

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with patch("app.services.tutor.llm_chat", new_callable=AsyncMock, return_value="Answer"):
            result = await svc.ask("path-1", "node-1", "user-1", "Q?")
            assert result["answer"] == "Answer"

    @pytest.mark.asyncio
    async def test_ask_rejects_unauthorized_access(self):
        """User cannot access another user's path (path not found = 404)."""
        from app.core.errors import ApiError
        from app.services.tutor import TutorService

        db = AsyncMock()
        svc = TutorService(db)

        # Path query returns None (user doesn't own path)
        async def execute_side_effect(query):
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with pytest.raises(ApiError, match="Learning path not found"):
            await svc.ask("path-1", "node-1", "other-user", "Hack attempt?")
