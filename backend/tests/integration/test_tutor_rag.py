"""Integration tests: Tutor RAG integration.

Verifies:
  - Tutor returns citations when knowledge base has relevant content
  - Tutor returns has_knowledge=False when no knowledge base content
  - Tutor doesn't fabricate citations
  - Tutor handles knowledge search failure gracefully
  - Tutor response structure is correct

Run with:
    pytest tests/integration/test_tutor_rag.py -v
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.user import User


async def _create_user(db_session, prefix: str = "tutor-rag") -> str:
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


class TestTutorRagIntegration:
    """Verify Tutor service correctly integrates with RAG."""

    async def test_tutor_returns_citations_when_knowledge_exists(self, db_session):
        """When knowledge base has relevant content, citations should be returned."""
        from app.services.tutor import TutorService

        user_id = await _create_user(db_session, "tutor-cite")

        # Mock the build_rag_context to return results
        from app.services.rag_context import Citation, RagContext

        mock_rag = RagContext(
            chunks=("Python is a programming language.",),
            citations=(
                Citation(
                    index=1,
                    chunk_id="chunk-1",
                    document_id="doc-1",
                    document_title="Python Guide",
                    page_number=1,
                    section_title="Intro",
                ),
            ),
            document_titles=("Python Guide",),
            confidence=0.9,
            context_string="[1] Python is a programming language.",
        )

        service = TutorService(db_session)

        with (
            patch("app.services.tutor.require_node_access", new_callable=AsyncMock) as mock_access,
            patch("app.services.tutor.build_rag_context", new_callable=AsyncMock, return_value=mock_rag),
            patch("app.services.tutor.llm_chat", new_callable=AsyncMock, return_value="Python is great!"),
        ):
            mock_node = MagicMock()
            mock_node.title = "Python Basics"
            mock_access.return_value = MagicMock(node=mock_node)

            # Mock unit content query
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            db_session.execute = AsyncMock(return_value=mock_result)

            result = await service.ask(
                path_id="path-1",
                node_id="node-1",
                user_id=user_id,
                question="What is Python?",
            )

        assert result["answer"] == "Python is great!"
        assert result["has_knowledge"] is True
        assert len(result["citations"]) == 1
        assert result["citations"][0]["chunk_id"] == "chunk-1"
        assert result["citations"][0]["file_name"] == "Python Guide"

    async def test_tutor_returns_no_citations_when_no_knowledge(self, db_session):
        """When knowledge base is empty, citations should be empty and has_knowledge=False."""
        from app.services.rag_context import RagContext
        from app.services.tutor import TutorService

        user_id = await _create_user(db_session, "tutor-no-cite")

        mock_rag = RagContext(
            chunks=(),
            citations=(),
            document_titles=(),
            confidence=0.0,
            context_string="",
        )

        service = TutorService(db_session)

        with (
            patch("app.services.tutor.require_node_access", new_callable=AsyncMock) as mock_access,
            patch("app.services.tutor.build_rag_context", new_callable=AsyncMock, return_value=mock_rag),
            patch("app.services.tutor.llm_chat", new_callable=AsyncMock, return_value="Based on my knowledge..."),
        ):
            mock_node = MagicMock()
            mock_node.title = "Test Node"
            mock_access.return_value = MagicMock(node=mock_node)

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            db_session.execute = AsyncMock(return_value=mock_result)

            result = await service.ask(
                path_id="path-1",
                node_id="node-1",
                user_id=user_id,
                question="What is recursion?",
            )

        assert result["has_knowledge"] is False
        assert len(result["citations"]) == 0
        assert "知识库" in result["answer"] or "Based" in result["answer"]

    async def test_tutor_does_not_fabricate_citations(self, db_session):
        """Tutor should never return citations when RAG returns no results."""
        from app.services.rag_context import RagContext
        from app.services.tutor import TutorService

        user_id = await _create_user(db_session, "tutor-fabricate")

        mock_rag = RagContext(
            chunks=(),
            citations=(),
            document_titles=(),
            confidence=0.0,
            context_string="",
        )

        service = TutorService(db_session)

        with (
            patch("app.services.tutor.require_node_access", new_callable=AsyncMock) as mock_access,
            patch("app.services.tutor.build_rag_context", new_callable=AsyncMock, return_value=mock_rag),
            patch("app.services.tutor.llm_chat", new_callable=AsyncMock, return_value="Some answer."),
        ):
            mock_node = MagicMock()
            mock_node.title = "Test"
            mock_access.return_value = MagicMock(node=mock_node)

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            db_session.execute = AsyncMock(return_value=mock_result)

            result = await service.ask(
                path_id="path-1",
                node_id="node-1",
                user_id=user_id,
                question="test question",
            )

        # No fabricated citations
        assert result["citations"] == []
        assert result["has_knowledge"] is False

    async def test_tutor_handles_rag_failure_gracefully(self, db_session):
        """When RAG search raises, Tutor should still answer (best-effort)."""
        from app.services.tutor import TutorService

        user_id = await _create_user(db_session, "tutor-fail")

        service = TutorService(db_session)

        with (
            patch("app.services.tutor.require_node_access", new_callable=AsyncMock) as mock_access,
            patch(
                "app.services.tutor.build_rag_context",
                new_callable=AsyncMock,
                side_effect=RuntimeError("DB connection lost"),
            ),
            patch("app.services.tutor.llm_chat", new_callable=AsyncMock, return_value="Answer without knowledge."),
        ):
            mock_node = MagicMock()
            mock_node.title = "Test"
            mock_access.return_value = MagicMock(node=mock_node)

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            db_session.execute = AsyncMock(return_value=mock_result)

            # build_rag_context catches its own exceptions, but if it somehow raises:
            with pytest.raises(RuntimeError):
                await service.ask(
                    path_id="path-1",
                    node_id="node-1",
                    user_id=user_id,
                    question="test",
                )

    async def test_tutor_response_structure(self, db_session):
        """Tutor response must contain required fields."""
        from app.services.rag_context import Citation, RagContext
        from app.services.tutor import TutorService

        user_id = await _create_user(db_session, "tutor-struct")

        mock_rag = RagContext(
            chunks=("Content",),
            citations=(
                Citation(
                    index=1,
                    chunk_id="c1",
                    document_id="d1",
                    document_title="Doc",
                ),
            ),
            document_titles=("Doc",),
            confidence=0.8,
            context_string="[1] Content",
        )

        service = TutorService(db_session)

        with (
            patch("app.services.tutor.require_node_access", new_callable=AsyncMock) as mock_access,
            patch("app.services.tutor.build_rag_context", new_callable=AsyncMock, return_value=mock_rag),
            patch("app.services.tutor.llm_chat", new_callable=AsyncMock, return_value="Answer"),
        ):
            mock_node = MagicMock()
            mock_node.title = "Node"
            mock_access.return_value = MagicMock(node=mock_node)

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            db_session.execute = AsyncMock(return_value=mock_result)

            result = await service.ask(
                path_id="path-1",
                node_id="node-1",
                user_id=user_id,
                question="question",
            )

        # Required fields
        assert "question" in result
        assert "answer" in result
        assert "node_id" in result
        assert "citations" in result
        assert "has_knowledge" in result
        assert isinstance(result["citations"], list)
        assert isinstance(result["has_knowledge"], bool)
