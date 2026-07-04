"""Comprehensive unit tests for TutorService with RAG integration."""

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


def _make_knowledge_results(count=2):
    """Create mock knowledge search results."""
    results = []
    for i in range(count):
        results.append(
            {
                "id": f"chunk-{i + 1}",
                "document_id": f"doc-{i + 1}",
                "file_name": f"lecture_{i + 1}.pdf",
                "text": f"Knowledge chunk {i + 1} content about the topic.",
                "score": 0.9 - i * 0.1,
                "page_number": i + 1,
                "section_title": f"Section {i + 1}",
            }
        )
    return results


class TestTutorServiceAsk:
    """TutorService.ask tests with access guard and RAG integration."""

    @pytest.mark.asyncio
    async def test_ask_with_node_and_content(self):
        from app.services.tutor import TutorService

        db = AsyncMock()
        svc = TutorService(db)

        path = _make_path()
        version = _make_version()
        node = _make_node()
        content = _make_content()

        call_order = [path, version, node, content]

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            idx = min(call_count, len(call_order) - 1)
            call_count += 1
            return _mock_scalar_result(call_order[idx])

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with (
            patch("app.services.tutor.KnowledgeService") as mock_ks_cls,
            patch("app.services.tutor.llm_chat", new_callable=AsyncMock, return_value="Lists are great!"),
        ):
            mock_ks = AsyncMock()
            mock_ks.search = AsyncMock(return_value=[])
            mock_ks_cls.return_value = mock_ks

            result = await svc.ask("path-1", "node-1", "user-1", "What is a list?")
            assert result["question"] == "What is a list?"
            assert result["answer"] == "Lists are great!"
            assert result["node_id"] == "node-1"
            assert result["citations"] == []

    @pytest.mark.asyncio
    async def test_ask_without_node_provides_fallback_title(self):
        """When the queried node doesn't have a title, '未知节点' is used."""
        from app.services.tutor import TutorService

        db = AsyncMock()
        svc = TutorService(db)

        path = _make_path()
        version = _make_version()
        node = _make_node(title="")  # Empty title

        call_order = [path, version, node, None]

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            idx = min(call_count, len(call_order) - 1)
            call_count += 1
            return _mock_scalar_result(call_order[idx])

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with (
            patch("app.services.tutor.KnowledgeService") as mock_ks_cls,
            patch("app.services.tutor.llm_chat", new_callable=AsyncMock, return_value="An answer"),
        ):
            mock_ks = AsyncMock()
            mock_ks.search = AsyncMock(return_value=[])
            mock_ks_cls.return_value = mock_ks

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

        call_order = [path, version, node, content]

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            idx = min(call_count, len(call_order) - 1)
            call_count += 1
            return _mock_scalar_result(call_order[idx])

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with (
            patch("app.services.tutor.KnowledgeService") as mock_ks_cls,
            patch("app.services.tutor.llm_chat", new_callable=AsyncMock, return_value="Answer"),
        ):
            mock_ks = AsyncMock()
            mock_ks.search = AsyncMock(return_value=[])
            mock_ks_cls.return_value = mock_ks

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

        call_order = [path, version, node, content]

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            idx = min(call_count, len(call_order) - 1)
            call_count += 1
            return _mock_scalar_result(call_order[idx])

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with (
            patch("app.services.tutor.KnowledgeService") as mock_ks_cls,
            patch("app.services.tutor.llm_chat", new_callable=AsyncMock, return_value="Answer"),
        ):
            mock_ks = AsyncMock()
            mock_ks.search = AsyncMock(return_value=[])
            mock_ks_cls.return_value = mock_ks

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

        call_order = [path, version, node, None]

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            idx = min(call_count, len(call_order) - 1)
            call_count += 1
            return _mock_scalar_result(call_order[idx])

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with (
            patch("app.services.tutor.KnowledgeService") as mock_ks_cls,
            patch("app.services.tutor.llm_chat", new_callable=AsyncMock, side_effect=LLMError("API down")),
        ):
            mock_ks = AsyncMock()
            mock_ks.search = AsyncMock(return_value=[])
            mock_ks_cls.return_value = mock_ks

            result = await svc.ask("path-1", "node-1", "user-1", "Q?")
            assert "辅导服务暂时不可用" in result["answer"]
            assert "API down" not in result["answer"]  # Must not leak internal errors
            assert result["citations"] == []

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

        call_order = [path, version, node, content]

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            idx = min(call_count, len(call_order) - 1)
            call_count += 1
            return _mock_scalar_result(call_order[idx])

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with (
            patch("app.services.tutor.KnowledgeService") as mock_ks_cls,
            patch("app.services.tutor.llm_chat", new_callable=AsyncMock, return_value="Answer"),
        ):
            mock_ks = AsyncMock()
            mock_ks.search = AsyncMock(return_value=[])
            mock_ks_cls.return_value = mock_ks

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


class TestTutorServiceRAG:
    """Tests for the RAG (knowledge base) integration in TutorService."""

    @pytest.mark.asyncio
    async def test_rag_returns_citations_when_knowledge_found(self):
        """When knowledge search returns results, citations should be in the response."""
        from app.services.tutor import TutorService

        db = AsyncMock()
        svc = TutorService(db)

        path = _make_path()
        version = _make_version()
        node = _make_node()
        content = _make_content()

        call_order = [path, version, node, content]

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            idx = min(call_count, len(call_order) - 1)
            call_count += 1
            return _mock_scalar_result(call_order[idx])

        db.execute = AsyncMock(side_effect=execute_side_effect)

        knowledge_results = _make_knowledge_results(3)

        with (
            patch("app.services.tutor.KnowledgeService") as mock_ks_cls,
            patch("app.services.tutor.llm_chat", new_callable=AsyncMock, return_value="Based on [1], lists are..."),
        ):
            mock_ks = AsyncMock()
            mock_ks.search = AsyncMock(return_value=knowledge_results)
            mock_ks_cls.return_value = mock_ks

            result = await svc.ask("path-1", "node-1", "user-1", "What is a list?")

            assert result["answer"] == "Based on [1], lists are..."
            assert len(result["citations"]) == 3

            # Verify citation structure
            cit = result["citations"][0]
            assert cit["index"] == 1
            assert cit["chunk_id"] == "chunk-1"
            assert cit["document_id"] == "doc-1"
            assert cit["file_name"] == "lecture_1.pdf"
            assert cit["page_number"] == 1
            assert cit["section_title"] == "Section 1"

            # Verify knowledge service was called with user_id and question
            mock_ks.search.assert_called_once_with(
                user_id="user-1",
                query="What is a list?",
                limit=5,
            )

    @pytest.mark.asyncio
    async def test_rag_empty_results_still_answers(self):
        """When knowledge search returns no results, answer from unit content only."""
        from app.services.tutor import TutorService

        db = AsyncMock()
        svc = TutorService(db)

        path = _make_path()
        version = _make_version()
        node = _make_node()
        content = _make_content()

        call_order = [path, version, node, content]

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            idx = min(call_count, len(call_order) - 1)
            call_count += 1
            return _mock_scalar_result(call_order[idx])

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with (
            patch("app.services.tutor.KnowledgeService") as mock_ks_cls,
            patch("app.services.tutor.llm_chat", new_callable=AsyncMock, return_value="Answer from unit content"),
        ):
            mock_ks = AsyncMock()
            mock_ks.search = AsyncMock(return_value=[])
            mock_ks_cls.return_value = mock_ks

            result = await svc.ask("path-1", "node-1", "user-1", "Q?")

            assert result["answer"] == "Answer from unit content"
            assert result["citations"] == []

    @pytest.mark.asyncio
    async def test_rag_search_failure_does_not_block_answer(self):
        """If knowledge search raises, the tutor should still answer from unit content."""
        from app.services.tutor import TutorService

        db = AsyncMock()
        svc = TutorService(db)

        path = _make_path()
        version = _make_version()
        node = _make_node()
        content = _make_content()

        call_order = [path, version, node, content]

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            idx = min(call_count, len(call_order) - 1)
            call_count += 1
            return _mock_scalar_result(call_order[idx])

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with (
            patch("app.services.tutor.KnowledgeService") as mock_ks_cls,
            patch("app.services.tutor.llm_chat", new_callable=AsyncMock, return_value="Fallback answer"),
        ):
            mock_ks = AsyncMock()
            mock_ks.search = AsyncMock(side_effect=RuntimeError("DB connection lost"))
            mock_ks_cls.return_value = mock_ks

            result = await svc.ask("path-1", "node-1", "user-1", "Q?")

            assert result["answer"] == "Fallback answer"
            assert result["citations"] == []

    @pytest.mark.asyncio
    async def test_rag_token_budget_limits_context(self):
        """When knowledge chunks exceed the char budget, only a subset is cited."""
        from app.services.tutor import TutorService

        db = AsyncMock()
        svc = TutorService(db)

        path = _make_path()
        version = _make_version()
        node = _make_node()
        content = _make_content()

        call_order = [path, version, node, content]

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            idx = min(call_count, len(call_order) - 1)
            call_count += 1
            return _mock_scalar_result(call_order[idx])

        db.execute = AsyncMock(side_effect=execute_side_effect)

        # Create chunks that individually fit but collectively exceed budget
        big_chunks = [
            {
                "id": f"chunk-{i}",
                "document_id": f"doc-{i}",
                "file_name": f"file_{i}.pdf",
                "text": "A" * 3000,  # 3000 chars each
                "score": 0.9,
                "page_number": i,
                "section_title": None,
            }
            for i in range(5)
        ]

        with (
            patch("app.services.tutor.KnowledgeService") as mock_ks_cls,
            patch("app.services.tutor.llm_chat", new_callable=AsyncMock, return_value="Answer"),
        ):
            mock_ks = AsyncMock()
            mock_ks.search = AsyncMock(return_value=big_chunks)
            mock_ks_cls.return_value = mock_ks

            result = await svc.ask("path-1", "node-1", "user-1", "Q?")

            # 6000 char budget / ~3000 per chunk ≈ at most 2 chunks
            assert len(result["citations"]) <= 2
            assert len(result["citations"]) >= 1

    @pytest.mark.asyncio
    async def test_rag_citations_have_correct_indices(self):
        """Citations should be numbered sequentially starting from 1."""
        from app.services.tutor import TutorService

        db = AsyncMock()
        svc = TutorService(db)

        path = _make_path()
        version = _make_version()
        node = _make_node()
        content = _make_content()

        call_order = [path, version, node, content]

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            idx = min(call_count, len(call_order) - 1)
            call_count += 1
            return _mock_scalar_result(call_order[idx])

        db.execute = AsyncMock(side_effect=execute_side_effect)

        knowledge_results = _make_knowledge_results(4)

        with (
            patch("app.services.tutor.KnowledgeService") as mock_ks_cls,
            patch("app.services.tutor.llm_chat", new_callable=AsyncMock, return_value="Answer"),
        ):
            mock_ks = AsyncMock()
            mock_ks.search = AsyncMock(return_value=knowledge_results)
            mock_ks_cls.return_value = mock_ks

            result = await svc.ask("path-1", "node-1", "user-1", "Q?")

            indices = [c["index"] for c in result["citations"]]
            assert indices == [1, 2, 3, 4]

    @pytest.mark.asyncio
    async def test_rag_citation_optional_fields_omitted_when_null(self):
        """When page_number or section_title is None, they should be omitted from citations."""
        from app.services.tutor import TutorService

        db = AsyncMock()
        svc = TutorService(db)

        path = _make_path()
        version = _make_version()
        node = _make_node()
        content = _make_content()

        call_order = [path, version, node, content]

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            idx = min(call_count, len(call_order) - 1)
            call_count += 1
            return _mock_scalar_result(call_order[idx])

        db.execute = AsyncMock(side_effect=execute_side_effect)

        knowledge_results = [
            {
                "id": "chunk-1",
                "document_id": "doc-1",
                "file_name": "plain.txt",
                "text": "Some content",
                "score": 0.9,
                "page_number": None,
                "section_title": None,
            }
        ]

        with (
            patch("app.services.tutor.KnowledgeService") as mock_ks_cls,
            patch("app.services.tutor.llm_chat", new_callable=AsyncMock, return_value="Answer"),
        ):
            mock_ks = AsyncMock()
            mock_ks.search = AsyncMock(return_value=knowledge_results)
            mock_ks_cls.return_value = mock_ks

            result = await svc.ask("path-1", "node-1", "user-1", "Q?")

            cit = result["citations"][0]
            assert cit["index"] == 1
            assert cit["chunk_id"] == "chunk-1"
            assert cit["file_name"] == "plain.txt"
            assert "page_number" not in cit
            assert "section_title" not in cit
