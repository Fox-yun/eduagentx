"""Comprehensive unit tests for TutorService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _mock_scalar_result(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


class TestTutorServiceAsk:
    @pytest.mark.asyncio
    async def test_ask_with_node_and_content(self):
        from app.services.tutor import TutorService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = TutorService(db)

        node = MagicMock()
        node.id = "node-1"
        node.title = "Python Lists"

        content = MagicMock()
        content.content = {
            "sections": [
                {"title": "Intro", "content": "Lists are ordered collections..."},
                {"title": "Operations", "content": "You can append, remove..."},
            ]
        }

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(node)
            elif call_count == 2:
                return _mock_scalar_result(content)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with patch("app.services.tutor.llm_chat", new_callable=AsyncMock, return_value="Lists are great!"):
            result = await svc.ask("path-1", "node-1", "user-1", "What is a list?")
            assert result["question"] == "What is a list?"
            assert result["answer"] == "Lists are great!"
            assert result["node_id"] == "node-1"

    @pytest.mark.asyncio
    async def test_ask_without_node(self):
        from app.services.tutor import TutorService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = TutorService(db)

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(None)  # no node
            elif call_count == 2:
                return _mock_scalar_result(None)  # no content
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with patch("app.services.tutor.llm_chat", new_callable=AsyncMock, return_value="An answer"):
            result = await svc.ask("path-1", "bad-node", "user-1", "Hello?")
            assert result["answer"] == "An answer"

    @pytest.mark.asyncio
    async def test_ask_with_content_no_sections(self):
        from app.services.tutor import TutorService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = TutorService(db)

        node = MagicMock()
        node.title = "Test"

        content = MagicMock()
        content.content = {"sections": []}

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(node)
            elif call_count == 2:
                return _mock_scalar_result(content)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with patch("app.services.tutor.llm_chat", new_callable=AsyncMock, return_value="Answer"):
            result = await svc.ask("path-1", "node-1", "user-1", "Question?")
            assert result["answer"] == "Answer"

    @pytest.mark.asyncio
    async def test_ask_with_content_no_content_field(self):
        from app.services.tutor import TutorService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = TutorService(db)

        node = MagicMock()
        node.title = "Test"

        content = MagicMock()
        content.content = None

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(node)
            elif call_count == 2:
                return _mock_scalar_result(content)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with patch("app.services.tutor.llm_chat", new_callable=AsyncMock, return_value="Answer"):
            result = await svc.ask("path-1", "node-1", "user-1", "Q?")
            assert result["answer"] == "Answer"

    @pytest.mark.asyncio
    async def test_ask_llm_error_returns_fallback(self):
        from app.services.llm import LLMError
        from app.services.tutor import TutorService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = TutorService(db)

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1 or call_count == 2:
                return _mock_scalar_result(None)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with patch("app.services.tutor.llm_chat", new_callable=AsyncMock, side_effect=LLMError("API down")):
            result = await svc.ask("path-1", "node-1", "user-1", "Q?")
            assert "抱歉" in result["answer"]
            assert "API down" in result["answer"]

    @pytest.mark.asyncio
    async def test_ask_with_many_sections_truncated(self):
        from app.services.tutor import TutorService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = TutorService(db)

        node = MagicMock()
        node.title = "Test"

        content = MagicMock()
        content.content = {"sections": [{"title": f"Section {i}", "content": f"Content {i}" * 100} for i in range(10)]}

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(node)
            elif call_count == 2:
                return _mock_scalar_result(content)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with patch("app.services.tutor.llm_chat", new_callable=AsyncMock, return_value="Answer"):
            result = await svc.ask("path-1", "node-1", "user-1", "Q?")
            assert result["answer"] == "Answer"
