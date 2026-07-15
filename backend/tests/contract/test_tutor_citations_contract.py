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
            patch(
                "app.services.tutor.build_rag_context", new_callable=AsyncMock, return_value=_make_rag_with_citations()
            ),
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
            patch(
                "app.services.tutor.build_rag_context", new_callable=AsyncMock, return_value=_make_rag_with_citations()
            ),
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
            patch(
                "app.services.tutor.build_rag_context", new_callable=AsyncMock, return_value=_make_rag_with_citations()
            ),
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
            patch(
                "app.services.tutor.build_rag_context", new_callable=AsyncMock, return_value=_make_rag_with_citations()
            ),
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
            patch(
                "app.services.tutor.build_rag_context", new_callable=AsyncMock, return_value=_make_rag_with_citations()
            ),
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

    @pytest.mark.asyncio
    async def test_multimodal_response_contains_artifacts_and_agent_trace(self):
        """Requested tutor modalities must be structured and explainable."""
        from app.services.tutor import TutorService

        mock_db = AsyncMock()
        service = TutorService(mock_db)

        with (
            patch("app.services.tutor.require_node_access", new_callable=AsyncMock) as mock_access,
            patch("app.services.tutor.build_rag_context", new_callable=AsyncMock, return_value=_make_rag_empty()),
            patch(
                "app.services.tutor.llm_chat",
                new_callable=AsyncMock,
                return_value="先理解变量，再运行一个例子，最后修改输入观察结果。",
            ),
            patch(
                "app.services.tutor.llm_json",
                new_callable=AsyncMock,
                return_value={
                    "diagram": {
                        "title": "变量绑定关系图",
                        "diagram_type": "concept_map",
                        "summary": "变量名通过引用指向对象。",
                        "groups": [],
                        "nodes": [
                            {"id": "q", "label": "变量是什么", "detail": "聚焦名称与对象", "kind": "question"},
                            {"id": "n1", "label": "名称绑定", "detail": "名称指向对象", "kind": "concept"},
                            {"id": "n2", "label": "共享引用", "detail": "多个名称可指向同一对象", "kind": "concept"},
                            {"id": "p", "label": "运行验证", "detail": "使用 is 检查身份", "kind": "practice"},
                        ],
                        "edges": [
                            {"source": "q", "target": "n1", "label": "建立关系"},
                            {"source": "n1", "target": "n2", "label": "扩展"},
                            {"source": "n2", "target": "p", "label": "验证"},
                        ],
                    },
                    "code_example": {
                        "title": "变量引用示例",
                        "language": "python",
                        "code": "values = [1, 2]\nalias = values\nalias.append(3)\nprint(values)",
                        "expected_output": "[1, 2, 3]",
                        "explanation": "修改共享对象后两个名称都能观察到变化。",
                        "walkthrough": ["创建列表", "建立共享引用", "修改并观察"],
                        "challenge": "重新绑定 alias 后再次比较。",
                    },
                    "storyboard": {
                        "title": "变量引用动画",
                        "estimated_seconds": 18,
                        "scenes": [
                            {"title": "创建", "visual": "名称与对象出现", "narration": "创建列表对象。", "duration_seconds": 6, "keywords": ["对象"]},
                            {"title": "共享", "visual": "两条箭头指向同一对象", "narration": "两个名称共享引用。", "duration_seconds": 6, "keywords": ["引用"]},
                            {"title": "验证", "visual": "列表内容发生变化", "narration": "修改对象并核对输出。", "duration_seconds": 6, "keywords": ["验证"]},
                        ],
                    },
                },
            ),
        ):
            mock_node = MagicMock()
            mock_node.title = "Python 变量"
            mock_access.return_value = MagicMock(node=mock_node)

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute = AsyncMock(return_value=mock_result)

            result = await service.ask(
                "path-1",
                "node-1",
                "user-1",
                "请用图、代码和动画解释变量",
                response_modes=["diagram", "code", "storyboard"],
            )

        assert result["modalities"] == ["text", "diagram", "code", "storyboard"]
        assert result["diagram"]["nodes"][0]["kind"] == "question"
        assert result["diagram"]["diagram_type"] == "concept_map"
        assert result["diagram"]["summary"] == "变量名通过引用指向对象。"
        assert result["diagram"]["edges"][0]["label"] == "建立关系"
        assert result["code_example"]["language"] == "python"
        assert result["code_example"]["expected_output"] == "[1, 2, 3]"
        assert len(result["storyboard"]["scenes"]) == 3
        assert result["storyboard"]["scenes"][0]["duration_seconds"] == 6
        assert result["quality"]["safety_checked"] is True
        roles = {step["agent"] for step in result["agent_trace"]}
        assert {
            "intent_analyzer",
            "knowledge_retriever",
            "personalized_tutor",
            "visual_explainer",
            "code_coach",
            "storyboard_director",
            "quality_reviewer",
        }.issubset(roles)
