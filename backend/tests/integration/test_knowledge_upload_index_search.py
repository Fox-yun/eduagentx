"""Integration tests: Knowledge upload, index, and search runtime.

Verifies the full knowledge pipeline:
  - TXT upload → index → search hit
  - PDF upload → index → search hit
  - DOCX upload → index → search hit
  - Index completion transitions document to 'ready'
  - Search only returns results from 'ready' documents

These tests require a running PostgreSQL with the tsv trigger.
Run with:
    pytest tests/integration/test_knowledge_upload_index_search.py -v
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.models.user import User
from app.services.knowledge import KnowledgeService
from app.services.storage import InMemoryObjectStorage


async def _create_user(db_session, prefix: str = "kb-runtime") -> str:
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


async def _create_document(
    db_session,
    user_id: str,
    title: str,
    filename: str,
    mime_type: str,
    content: bytes,
    storage: InMemoryObjectStorage,
) -> str:
    """Create a document and upload content to storage."""
    storage_key = f"knowledge/{user_id}/{uuid.uuid4()}_{filename}"
    await storage.put(storage_key, content, mime_type)

    service = KnowledgeService(db_session, storage=storage)
    doc = await service.create_document(
        user_id=user_id,
        title=title,
        filename=filename,
        mime_type=mime_type,
        size_bytes=len(content),
        storage_key=storage_key,
    )
    await db_session.commit()
    return doc.id


async def _index_document(db_session, doc_id: str, storage: InMemoryObjectStorage) -> None:
    """Run the knowledge index pipeline for a document."""
    from app.models.task import BackgroundTask
    from app.workers.tasks import _execute_knowledge_index

    task = BackgroundTask(
        id=str(uuid.uuid4()),
        user_id="system",
        task_type="knowledge_index",
        target_type="document",
        target_id=doc_id,
        status="pending",
    )
    db_session.add(task)
    await db_session.commit()


    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.services.storage.get_object_storage", lambda: storage)
        await _execute_knowledge_index(db_session, task)


class TestKnowledgeUploadIndexSearch:
    """Verify knowledge upload → index → search pipeline."""

    async def test_txt_upload_index_search(self, db_session):
        """TXT file: upload → index → search should find content."""
        storage = InMemoryObjectStorage()
        user_id = await _create_user(db_session, "kb-txt")

        content = b"Python is a powerful programming language for data science and web development."
        doc_id = await _create_document(
            db_session,
            user_id,
            title="Python Guide",
            filename="python.txt",
            mime_type="text/plain",
            content=content,
            storage=storage,
        )

        await _index_document(db_session, doc_id, storage)

        # Verify document is ready
        service = KnowledgeService(db_session, storage=storage)
        doc = await service.get_document(doc_id, user_id)
        assert doc.status == "ready"

        # Search should find content
        results = await service.search(user_id=user_id, query="Python programming")
        assert len(results) > 0
        assert "Python" in results[0]["text"] or "python" in results[0]["text"].lower()

    async def test_pdf_upload_index_search(self, db_session):
        """PDF file: upload → index → search should find content."""
        storage = InMemoryObjectStorage()
        user_id = await _create_user(db_session, "kb-pdf")

        # Minimal valid PDF with text content
        pdf_content = b"""%PDF-1.0
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj
4 0 obj
<< /Length 44 >>
stream
BT /F1 12 Tf 100 700 Td (Algorithms and Data Structures) Tj ET
endstream
endobj
5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000266 00000 n
0000000360 00000 n
trailer
<< /Size 6 /Root 1 0 R >>
startxref
429
%%EOF"""

        doc_id = await _create_document(
            db_session,
            user_id,
            title="Algorithms PDF",
            filename="algorithms.pdf",
            mime_type="application/pdf",
            content=pdf_content,
            storage=storage,
        )

        await _index_document(db_session, doc_id, storage)

        service = KnowledgeService(db_session, storage=storage)
        doc = await service.get_document(doc_id, user_id)
        assert doc.status == "ready"

        results = await service.search(user_id=user_id, query="Algorithms")
        assert len(results) > 0

    async def test_docx_upload_index_search(self, db_session):
        """DOCX file: upload → index → search should find content."""
        storage = InMemoryObjectStorage()
        user_id = await _create_user(db_session, "kb-docx")

        # Create a minimal DOCX (zip with word/document.xml)
        import io
        import zipfile

        docx_buf = io.BytesIO()
        with zipfile.ZipFile(docx_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "[Content_Types].xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                "</Types>",
            )
            zf.writestr(
                "word/document.xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body><w:p><w:r><w:t>Machine learning models require training data.</w:t></w:r></w:p>"
                "</w:body></w:document>",
            )
            zf.writestr(
                "_rels/.rels",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                "</Relationships>",
            )

        docx_content = docx_buf.getvalue()

        doc_id = await _create_document(
            db_session,
            user_id,
            title="ML Notes",
            filename="ml_notes.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            content=docx_content,
            storage=storage,
        )

        await _index_document(db_session, doc_id, storage)

        service = KnowledgeService(db_session, storage=storage)
        doc = await service.get_document(doc_id, user_id)
        assert doc.status == "ready"

        results = await service.search(user_id=user_id, query="Machine learning")
        assert len(results) > 0

    async def test_search_returns_empty_for_non_ready_documents(self, db_session):
        """Search should only return results from 'ready' documents."""
        storage = InMemoryObjectStorage()
        user_id = await _create_user(db_session, "kb-notready")

        # Create a document but don't index it (stays in 'uploaded' status)
        content = b"This content should not be searchable yet."
        await _create_document(
            db_session,
            user_id,
            title="Not Indexed",
            filename="not_indexed.txt",
            mime_type="text/plain",
            content=content,
            storage=storage,
        )

        # Search should return no results (document not ready)
        service = KnowledgeService(db_session, storage=storage)
        results = await service.search(user_id=user_id, query="content")
        assert len(results) == 0
