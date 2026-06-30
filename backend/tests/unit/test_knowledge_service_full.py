"""Comprehensive unit tests for KnowledgeService."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors import ApiError


def _mock_scalar_result(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _mock_scalars(items):
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


def _mock_scalar(value):
    r = MagicMock()
    r.scalar.return_value = value
    return r


def _mock_all(rows):
    r = MagicMock()
    r.all.return_value = rows
    return r


def _make_doc(**overrides):
    d = MagicMock()
    d.id = overrides.get("id", "doc-1")
    d.user_id = overrides.get("user_id", "user-1")
    d.scope = overrides.get("scope", "personal")
    d.title = overrides.get("title", "Test Doc")
    d.filename = overrides.get("filename", "test.pdf")
    d.mime_type = overrides.get("mime_type", "application/pdf")
    d.size_bytes = overrides.get("size_bytes", 1024)
    d.storage_key = overrides.get("storage_key", "/uploads/test.pdf")
    d.status = overrides.get("status", "uploaded")
    d.operation_status = overrides.get("operation_status", "idle")
    d.checksum = overrides.get("checksum", "abc123")
    d.error = overrides.get("error")
    d.index_task_id = overrides.get("index_task_id")
    d.created_at = overrides.get("created_at", datetime.now(UTC))
    d.updated_at = overrides.get("updated_at", datetime.now(UTC))
    return d


def _make_chunk(**overrides):
    c = MagicMock()
    c.id = overrides.get("id", "chunk-1")
    c.document_id = overrides.get("document_id", "doc-1")
    c.chunk_index = overrides.get("chunk_index", 0)
    c.content = overrides.get("content", "Some text content")
    c.token_count = overrides.get("token_count", 10)
    c.page_number = overrides.get("page_number", 1)
    c.section_title = overrides.get("section_title")
    c.embedding = overrides.get("embedding")
    c.metadata = overrides.get("metadata")
    return c


class TestKnowledgeServiceCreateDocument:
    @pytest.mark.asyncio
    async def test_create_document_happy_path(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = KnowledgeService(db)

        doc = await svc.create_document(
            user_id="user-1",
            title="My PDF",
            filename="test.pdf",
            mime_type="application/pdf",
            size_bytes=1024,
            storage_key="/uploads/test.pdf",
        )
        assert doc is not None
        db.add.assert_called()
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_create_document_invalid_mime(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = KnowledgeService(db)

        with pytest.raises(ApiError) as exc_info:
            await svc.create_document(
                user_id="user-1",
                title="Bad File",
                filename="test.exe",
                mime_type="application/octet-stream",
                size_bytes=1024,
                storage_key="/uploads/test.exe",
            )
        assert exc_info.value.code == "INVALID_MIME_TYPE"
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_create_document_too_large(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = KnowledgeService(db)

        with pytest.raises(ApiError) as exc_info:
            await svc.create_document(
                user_id="user-1",
                title="Big File",
                filename="big.pdf",
                mime_type="application/pdf",
                size_bytes=100 * 1024 * 1024,  # 100MB
                storage_key="/uploads/big.pdf",
            )
        assert exc_info.value.code == "FILE_TOO_LARGE"

    @pytest.mark.asyncio
    async def test_create_document_with_checksum(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = KnowledgeService(db)

        doc = await svc.create_document(
            user_id="user-1",
            title="My Doc",
            filename="doc.txt",
            mime_type="text/plain",
            size_bytes=500,
            storage_key="/uploads/doc.txt",
            checksum="sha256abc",
            scope="shared",
        )
        assert doc.checksum == "sha256abc"
        assert doc.scope == "shared"

    @pytest.mark.asyncio
    async def test_create_document_all_allowed_mimes(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = KnowledgeService(db)

        allowed = [
            "application/pdf",
            "text/plain",
            "text/markdown",
            "text/csv",
            "application/json",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ]
        for mime in allowed:
            doc = await svc.create_document(
                user_id="user-1",
                title="Doc",
                filename="file",
                mime_type=mime,
                size_bytes=100,
                storage_key="/key",
            )
            assert doc is not None


class TestKnowledgeServiceGetDocument:
    @pytest.mark.asyncio
    async def test_get_document_found(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = KnowledgeService(db)
        doc = _make_doc()
        db.execute = AsyncMock(return_value=_mock_scalar_result(doc))

        result = await svc.get_document("doc-1", "user-1")
        assert result is doc

    @pytest.mark.asyncio
    async def test_get_document_not_found(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = KnowledgeService(db)
        db.execute = AsyncMock(return_value=_mock_scalar_result(None))

        with pytest.raises(ApiError) as exc_info:
            await svc.get_document("nonexistent", "user-1")
        assert exc_info.value.code == "DOCUMENT_NOT_FOUND"


class TestKnowledgeServiceListDocuments:
    @pytest.mark.asyncio
    async def test_list_documents_no_cursor(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = KnowledgeService(db)
        docs = [_make_doc(id=f"doc-{i}") for i in range(3)]

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar(3)
            elif call_count == 2:
                return _mock_scalars(docs)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await svc.list_documents("user-1")
        assert len(result["items"]) == 3
        assert result["total"] == 3

    @pytest.mark.asyncio
    async def test_list_documents_with_next_page(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = KnowledgeService(db)
        docs = [_make_doc(id=f"doc-{i}", created_at=datetime.now(UTC)) for i in range(21)]

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar(25)
            elif call_count == 2:
                return _mock_scalars(docs)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await svc.list_documents("user-1", limit=20)
        assert len(result["items"]) == 20
        assert result["next_cursor"] is not None

    @pytest.mark.asyncio
    async def test_list_documents_invalid_limit(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = KnowledgeService(db)

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar(0)
            elif call_count == 2:
                return _mock_scalars([])
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await svc.list_documents("user-1", limit=200)
        assert result["items"] == []


class TestKnowledgeServiceDeleteDocument:
    @pytest.mark.asyncio
    async def test_delete_document_happy_path(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = KnowledgeService(db)
        doc = _make_doc(status="ready")
        db.execute = AsyncMock(return_value=_mock_scalar_result(doc))

        await svc.delete_document("doc-1", "user-1")
        assert doc.status == "deleted"
        assert doc.operation_status == "idle"
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_delete_document_invalid_status(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = KnowledgeService(db)
        doc = _make_doc(status="deleted")  # already deleted
        db.execute = AsyncMock(return_value=_mock_scalar_result(doc))

        with pytest.raises(ApiError) as exc_info:
            await svc.delete_document("doc-1", "user-1")
        assert exc_info.value.code == "INVALID_STATUS"


class TestKnowledgeServiceUpdateDocumentStatus:
    @pytest.mark.asyncio
    async def test_update_status_happy_path(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = KnowledgeService(db)
        doc = _make_doc(status="uploaded")
        db.execute = AsyncMock(return_value=_mock_scalar_result(doc))

        result = await svc.update_document_status("doc-1", "scanning", operation_status="parsing")
        assert result.status == "scanning"
        assert result.operation_status == "parsing"

    @pytest.mark.asyncio
    async def test_update_status_with_error(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = KnowledgeService(db)
        doc = _make_doc(status="uploaded")
        db.execute = AsyncMock(return_value=_mock_scalar_result(doc))

        result = await svc.update_document_status("doc-1", "failed", error="Parse error")
        assert result.status == "failed"
        assert result.error == "Parse error"

    @pytest.mark.asyncio
    async def test_update_status_not_found(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = KnowledgeService(db)
        db.execute = AsyncMock(return_value=_mock_scalar_result(None))

        with pytest.raises(ApiError) as exc_info:
            await svc.update_document_status("nonexistent", "scanning")
        assert exc_info.value.code == "DOCUMENT_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_update_status_invalid_transition(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = KnowledgeService(db)
        doc = _make_doc(status="uploaded")
        db.execute = AsyncMock(return_value=_mock_scalar_result(doc))

        with pytest.raises(ApiError) as exc_info:
            await svc.update_document_status("doc-1", "ready")  # uploaded -> ready is invalid
        assert exc_info.value.code == "INVALID_TRANSITION"


class TestKnowledgeServiceAddChunks:
    @pytest.mark.asyncio
    async def test_add_chunks_from_start(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = KnowledgeService(db)
        db.execute = AsyncMock(return_value=_mock_scalar_result(None))  # no existing chunks

        chunks_data = [
            {"content": "Chunk 1", "token_count": 10, "page_number": 1},
            {"content": "Chunk 2", "token_count": 15, "page_number": 2},
        ]
        result = await svc.add_chunks("doc-1", chunks_data)
        assert len(result) == 2
        assert db.add.call_count == 2
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_add_chunks_append(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = KnowledgeService(db)
        existing_chunk = _make_chunk(chunk_index=5)
        db.execute = AsyncMock(return_value=_mock_scalar_result(existing_chunk))

        chunks_data = [{"content": "New chunk"}]
        result = await svc.add_chunks("doc-1", chunks_data)
        assert len(result) == 1
        assert result[0].chunk_index == 6


class TestKnowledgeServiceSearch:
    @pytest.mark.asyncio
    async def test_search_no_docs(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = KnowledgeService(db)

        mock_result = MagicMock()
        mock_result.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        result = await svc.search("user-1", "test query")
        assert result == []

    @pytest.mark.asyncio
    async def test_search_with_results(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = KnowledgeService(db)
        chunk = _make_chunk(content="matching content")

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # doc IDs
                mock = MagicMock()
                mock.all.return_value = [("doc-1",)]
                return mock
            elif call_count == 2:  # chunk search
                return _mock_scalars([chunk])
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await svc.search("user-1", "matching")
        assert len(result) == 1
        assert result[0]["text"] == "matching content"
        assert result[0]["score"] == 0.5

    @pytest.mark.asyncio
    async def test_search_invalid_limit(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = KnowledgeService(db)

        mock_result = MagicMock()
        mock_result.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        result = await svc.search("user-1", "q", limit=0)
        assert result == []

    @pytest.mark.asyncio
    async def test_search_with_scope(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = KnowledgeService(db)

        mock_result = MagicMock()
        mock_result.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        result = await svc.search("user-1", "q", scope="personal")
        assert result == []


class TestKnowledgeServiceFormatDocument:
    def test_format_document_ready(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = KnowledgeService(db)
        doc = _make_doc(status="ready", operation_status="ready")

        result = svc._format_document(doc)
        assert result["status"] == "indexed"
        assert result["operation_status"] == "ready"

    def test_format_document_uploaded(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = KnowledgeService(db)
        doc = _make_doc(status="uploaded", operation_status="idle")

        result = svc._format_document(doc)
        assert result["status"] == "pending"
        assert result["operation_status"] == "ready"

    def test_format_document_failed(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = KnowledgeService(db)
        doc = _make_doc(status="failed", operation_status="failed", error="Parse error")

        result = svc._format_document(doc)
        assert result["status"] == "failed"
        assert result["error"] == "Parse error"
