"""Comprehensive unit tests for KnowledgeService."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors import ApiError
from app.services.storage import InMemoryObjectStorage


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
    d.active_index_version = overrides.get("active_index_version")
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
    c.index_version = overrides.get("index_version", 1)
    c.content_hash = overrides.get("content_hash", "hash123")
    return c


class TestKnowledgeServiceCreateDocument:
    @pytest.mark.asyncio
    async def test_create_document_happy_path(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
        db.add = MagicMock()  # sync method
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
        db.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_create_document_invalid_mime(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
        db.add = MagicMock()  # sync method
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
        db.add = MagicMock()  # sync method
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
        db.add = MagicMock()  # sync method
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
        db.add = MagicMock()  # sync method
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
        svc = KnowledgeService(db)
        doc = _make_doc()
        db.execute = AsyncMock(return_value=_mock_scalar_result(doc))

        result = await svc.get_document("doc-1", "user-1")
        assert result is doc

    @pytest.mark.asyncio
    async def test_get_document_not_found(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
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
        db.add = MagicMock()  # sync method
        storage = InMemoryObjectStorage()
        await storage.put("/uploads/test.pdf", b"content")
        svc = KnowledgeService(db, storage=storage)
        doc = _make_doc(status="ready", storage_key="/uploads/test.pdf")
        db.execute = AsyncMock(return_value=_mock_scalar_result(doc))

        await svc.delete_document("doc-1", "user-1")
        assert doc.status == "deleted"
        assert doc.operation_status == "idle"
        assert doc.active_index_version is None
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_delete_document_invalid_status(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
        storage = InMemoryObjectStorage()
        svc = KnowledgeService(db, storage=storage)
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
        svc = KnowledgeService(db)
        db.execute = AsyncMock(return_value=_mock_scalar_result(None))

        with pytest.raises(ApiError) as exc_info:
            await svc.update_document_status("nonexistent", "scanning")
        assert exc_info.value.code == "DOCUMENT_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_update_status_invalid_transition(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
        svc = KnowledgeService(db)
        doc = _make_doc(status="uploaded")
        db.execute = AsyncMock(return_value=_mock_scalar_result(doc))

        with pytest.raises(ApiError) as exc_info:
            await svc.update_document_status("doc-1", "ready")  # uploaded -> ready is invalid
        assert exc_info.value.code == "INVALID_TRANSITION"


class TestKnowledgeServiceAddChunks:
    @pytest.mark.asyncio
    async def test_add_chunks_basic(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
        db.add = MagicMock()  # sync method
        svc = KnowledgeService(db)

        chunks_data = [
            {"content": "Chunk 1", "chunk_index": 0, "token_count": 10, "page_number": 1},
            {"content": "Chunk 2", "chunk_index": 1, "token_count": 15, "page_number": 2},
        ]
        result = await svc.add_chunks("doc-1", chunks_data, index_version=1)
        assert len(result) == 2
        assert db.add.call_count == 2
        db.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_add_chunks_with_content_hash(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
        db.add = MagicMock()  # sync method
        svc = KnowledgeService(db)

        chunks_data = [
            {
                "content": "Some text",
                "chunk_index": 0,
                "token_count": 5,
                "content_hash": "abc123",
            },
        ]
        result = await svc.add_chunks("doc-1", chunks_data, index_version=2)
        assert len(result) == 1
        assert result[0].content_hash == "abc123"
        assert result[0].index_version == 2


class TestKnowledgeServiceSearch:
    @pytest.mark.asyncio
    async def test_search_no_docs(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
        svc = KnowledgeService(db)

        mock_result = MagicMock()
        mock_result.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        result = await svc.search("user-1", "test query")
        assert result == []

    @pytest.mark.asyncio
    async def test_search_empty_query(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
        svc = KnowledgeService(db)

        result = await svc.search("user-1", "  ")
        assert result == []

    @pytest.mark.asyncio
    async def test_search_invalid_limit(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
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
        svc = KnowledgeService(db)
        doc = _make_doc(status="ready", operation_status="ready")

        result = svc._format_document(doc)
        assert result["status"] == "indexed"
        assert result["operation_status"] == "ready"

    def test_format_document_uploaded(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
        svc = KnowledgeService(db)
        doc = _make_doc(status="uploaded", operation_status="idle")

        result = svc._format_document(doc)
        assert result["status"] == "pending"
        assert result["operation_status"] == "ready"

    def test_format_document_failed(self):
        from app.services.knowledge import KnowledgeService

        db = AsyncMock()
        svc = KnowledgeService(db)
        doc = _make_doc(status="failed", operation_status="failed", error="Parse error")

        result = svc._format_document(doc)
        assert result["status"] == "failed"
        assert result["error"] == "Parse error"


class TestDocumentParser:
    """Tests for document parsing."""

    def test_parse_txt(self):
        from app.services.document_parser import parse_document

        content = b"Hello world, this is a test."
        sections = parse_document(content, "text/plain")
        assert len(sections) == 1
        assert "Hello world" in sections[0].text

    def test_parse_markdown_with_headings(self):
        from app.services.document_parser import parse_document

        content = b"""# Title

Intro text.

## Section A

Content A.

## Section B

Content B.
"""
        sections = parse_document(content, "text/markdown")
        assert len(sections) >= 2
        # Sections should have titles
        titles = [s.section_title for s in sections if s.section_title]
        assert "Section A" in titles or "Section B" in titles

    def test_parse_json(self):
        from app.services.document_parser import parse_document

        content = b'{"key": "value", "list": [1, 2, 3]}'
        sections = parse_document(content, "application/json")
        assert len(sections) == 1
        assert "key" in sections[0].text

    def test_parse_csv(self):
        from app.services.document_parser import parse_document

        content = b"name,age\nAlice,30\nBob,25"
        sections = parse_document(content, "text/csv")
        assert len(sections) == 1
        assert "Alice" in sections[0].text

    def test_parse_unsupported_type(self):
        from app.services.document_parser import parse_document

        with pytest.raises(ValueError, match="Unsupported"):
            parse_document(b"content", "application/x-unknown")

    def test_parse_empty_txt(self):
        from app.services.document_parser import parse_document

        with pytest.raises(ValueError, match="empty"):
            parse_document(b"", "text/plain")


class TestChunker:
    """Tests for the text chunker."""

    def test_chunk_short_text(self):
        from app.services.chunker import chunk_sections
        from app.services.document_parser import ParsedSection

        section = ParsedSection(text="This is a short text that fits in one chunk.")
        chunks = chunk_sections([section])
        assert len(chunks) == 1
        assert chunks[0].chunk_index == 0
        assert chunks[0].content_hash != ""

    def test_chunk_long_text(self):
        from app.services.chunker import chunk_sections
        from app.services.document_parser import ParsedSection

        # Create text that will produce multiple chunks
        long_text = " ".join(["word"] * 2000)
        section = ParsedSection(text=long_text)
        chunks = chunk_sections([section])
        assert len(chunks) > 1
        # Verify deterministic: same input gives same output
        chunks2 = chunk_sections([section])
        assert len(chunks) == len(chunks2)
        for c1, c2 in zip(chunks, chunks2, strict=True):
            assert c1.content == c2.content
            assert c1.content_hash == c2.content_hash

    def test_chunk_preserves_page_number(self):
        from app.services.chunker import chunk_sections
        from app.services.document_parser import ParsedSection

        section = ParsedSection(text="Some content", page_number=5, section_title="Chapter 1")
        chunks = chunk_sections([section])
        assert chunks[0].page_number == 5
        assert chunks[0].section_title == "Chapter 1"

    def test_chunk_deterministic_hashes(self):
        from app.services.chunker import chunk_sections
        from app.services.document_parser import ParsedSection

        text = "Deterministic content for hashing test."
        section = ParsedSection(text=text)
        chunks1 = chunk_sections([section])
        chunks2 = chunk_sections([section])
        assert chunks1[0].content_hash == chunks2[0].content_hash


class TestInMemoryStorage:
    """Tests for InMemoryObjectStorage."""

    @pytest.mark.asyncio
    async def test_put_get_delete(self):
        from app.services.storage import InMemoryObjectStorage

        storage = InMemoryObjectStorage()
        await storage.put("key1", b"hello", "text/plain")
        assert await storage.exists("key1") is True

        data = await storage.get("key1")
        assert data == b"hello"

        await storage.delete("key1")
        assert await storage.exists("key1") is False

    @pytest.mark.asyncio
    async def test_get_not_found(self):
        from app.services.storage import InMemoryObjectStorage

        storage = InMemoryObjectStorage()
        with pytest.raises(KeyError):
            await storage.get("nonexistent")

    @pytest.mark.asyncio
    async def test_delete_idempotent(self):
        from app.services.storage import InMemoryObjectStorage

        storage = InMemoryObjectStorage()
        # Should not raise even if key doesn't exist
        await storage.delete("nonexistent")
