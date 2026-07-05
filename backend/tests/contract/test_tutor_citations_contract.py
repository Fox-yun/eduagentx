"""Contract tests: Tutor citations contract.

Verifies the API contract for tutor responses:
  - Response contains question, answer, node_id, citations, has_knowledge
  - Citations contain index, chunk_id, document_id, file_name
  - Citations never contain internal storage keys or raw paths
  - has_knowledge is a boolean
  - When has_knowledge is False, citations is empty

Run with:
    pytest tests/contract/test_tutor_citations_contract.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.rag_context import Citation, RagContext


def _make_rag_with_citations() -> RagContext:
    """Create a RagContext with sample citations."""
    return RagContext(
        chunks=("Python content", "More content"),
        citations=(
            Citation(
                index=1,
                chunk_id="chunk-abc",
                document_id="doc-123",
                document_title="Python Guide.pdf",
                page_number=5,
                section_title="Introduction",
            ),
            Citation(
                index=2,
                chunk_id="chunk-def",
                document_id="doc-456",
                document_title="Advanced Topics",
            ),
        ),
        document_titles=("Python Guide.pdf", "Advanced Topics"),
        confidence=0.85,
        context_string="[1] Python content\n\n[2] More content",
    )


def _make_rag_empty() -> RagContext:
    """Create an empty RagContext (no results)."""
    return RagContext(
        chunks=(),
        citations=(),
        document_titles=(),
        confidence=0.0,
        context_string="",
    )


class TestTutorCitationsContract:
    """Verify tutor response contract for citations."""

    @pytest.mark.asyncio
    async def test_response_contains_required_fields(self):
        """Tutor response must contain all required fields."""
        from app.services.tutor import TutorService

        mock_db = AsyncMock()
        service = TutorService(mock_db)

        with (
            patch("app.services.tutor.require_node_access", new_callable=AsyncMock) as mock_access,
            patch("app.services.tutor.build_rag_context", new_callable=AsyncMock, return_value=_make_rag_with_citations()),
            patch("app.services.tutor.llm_chat", new_callable=AsyncMock, return_value="Answer text"),
        ):
            mock_node = MagicMock()
            mock_node.title = "Test Node"
            mock_access.return_value = MagicMock(node=mock_node)

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute = AsyncMock(return_value=mock_result)

            result = await service.ask("path-1", "node-1", "user-1", "question")

        required_fields = {"question", "answer", "node_id", "citations", "has_knowledge"}
        assert required_fields.issubset(result.keys())

    @pytest.mark.asyncio
    async def test_citation_contains_required_fields(self):
        """Each citation must contain index, chunk_id, document_id, file_name."""
        from app.services.tutor import TutorService

        mock_db = AsyncMock()
        service = TutorService(mock_db)

        with (
            patch("app.services.tutor.require_node_access", new_callable=AsyncMock) as mock_access,
            patch("app.services.tutor.build_rag_context", new_callable=AsyncMock, return_value=_make_rag_with_citations()),
            patch("app.services.tutor.llm_chat", new_callable=AsyncMock, return_value="Answer"),
        ):
            mock_node = MagicMock()
            mock_node.title = "Node"
            mock_access.return_value = MagicMock(node=mock_node)

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute = AsyncMock(return_value=mock_result)

            result = await service.ask("path-1", "node-1", "user-1", "question")

        for citation in result["citations"]:
            assert "index" in citation
            assert "chunk_id" in citation
            assert "document_id" in citation
            assert "file_name" in citation

    @pytest.mark.asyncio
    async def test_citations_never_contain_storage_keys(self):
        """Citations must never contain internal storage keys or raw paths."""
        from app.services.tutor import TutorService

        mock_db = AsyncMock()
        service = TutorService(mock_db)

        with (
            patch("app.services.tutor.require_node_access", new_callable=AsyncMock) as mock_access,
            patch("app.services.tutor.build_rag_context", new_callable=AsyncMock, return_value=_make_rag_with_citations()),
            patch("app.services.tutor.llm_chat", new_callable=AsyncMock, return_value="Answer"),
        ):
            mock_node = MagicMock()
            mock_node.title = "Node"
            mock_access.return_value = MagicMock(node=mock_node)

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute = AsyncMock(return_value=mock_result)

            result = await service.ask("path-1", "node-1", "user-1", "question")

        forbidden_keys = {"storage_key", "internal_path", "raw_path", "private_key"}
        for citation in result["citations"]:
            for key in forbidden_keys:
                assert key not in citation, f"Citation should not contain '{key}'"

    @pytest.mark.asyncio
    async def test_has_knowledge_is_boolean(self):
        """has_knowledge must be a boolean."""
        from app.services.tutor import TutorService

        mock_db = AsyncMock()

        with (
            patch("app.services.tutor.require_node_access", new_callable=AsyncMock) as mock_access,
            patch("app.services.tutor.build_rag_context", new_callable=AsyncMock, return_value=_make_rag_with_citations()),
            patch("app.services.tutor.llm_chat", new_callable=AsyncMock, return_value="Answer"),
        ):
            mock_node = MagicMock()
            mock_node.title = "Node"
            mock_access.return_value = MagicMock(node=mock_node)

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute = AsyncMock(return_value=mock_result)

            service = TutorService(mock_db)
            result = await service.ask("path-1", "node-1", "user-1", "question")

        assert isinstance(result["has_knowledge"], bool)

    @pytest.mark.asyncio
    async def test_no_knowledge_means_empty_citations(self):
        """When has_knowledge is False, citations must be empty."""
        from app.services.tutor import TutorService

        mock_db = AsyncMock()

        with (
            patch("app.services.tutor.require_node_access", new_callable=AsyncMock) as mock_access,
            patch("app.services.tutor.build_rag_context", new_callable=AsyncMock, return_value=_make_rag_empty()),
            patch("app.services.tutor.llm_chat", new_callable=AsyncMock, return_value="Answer"),
        ):
            mock_node = MagicMock()
            mock_node.title = "Node"
            mock_access.return_value = MagicMock(node=mock_node)

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute = AsyncMock(return_value=mock_result)

            service = TutorService(mock_db)
            result = await service.ask("path-1", "node-1", "user-1", "question")

        assert result["has_knowledge"] is False
        assert result["citations"] == []

    @pytest.mark.asyncio
    async def test_has_knowledge_true_means_non_empty_citations(self):
        """When has_knowledge is True, citations should be non-empty."""
        from app.services.tutor import TutorService

        mock_db = AsyncMock()

        with (
            patch("app.services.tutor.require_node_access", new_callable=AsyncMock) as mock_access,
            patch("app.services.tutor.build_rag_context", new_callable=AsyncMock, return_value=_make_rag_with_citations()),
            patch("app.services.tutor.llm_chat", new_callable=AsyncMock, return_value="Answer"),
        ):
            mock_node = MagicMock()
            mock_node.title = "Node"
            mock_access.return_value = MagicMock(node=mock_node)

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute = AsyncMock(return_value=mock_result)

            service = TutorService(mock_db)
            result = await service.ask("path-1", "node-1", "user-1", "question")

        assert result["has_knowledge"] is True
        assert len(result["citations"]) > 0
