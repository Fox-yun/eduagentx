"""Integration tests: Knowledge delete cleans up chunks.

Verifies:
  - Delete marks document as 'deleted'
  - Delete removes all chunks from DB
  - Delete best-effort removes from object storage
  - Search no longer returns results for deleted documents

Run with:
    pytest tests/integration/test_knowledge_delete_cleanup.py -v
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models.knowledge import KnowledgeChunk
from app.models.user import User
from app.services.knowledge import KnowledgeService
from app.services.storage import InMemoryObjectStorage


async def _create_user(db_session, prefix: str = "kb-del") -> str:
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


async def _create_ready_document(
    db_session,
    user_id: str,
    storage: InMemoryObjectStorage,
    title: str = "Test Doc",
    filename: str = "test.txt",
    content: bytes = b"Test content for deletion testing.",
) -> str:
    """Create a document, upload to storage, and index it to 'ready'."""
    from app.models.task import BackgroundTask
    from app.workers.tasks import _execute_knowledge_index

    storage_key = f"knowledge/{user_id}/{uuid.uuid4()}_{filename}"
    await storage.put(storage_key, content, "text/plain")

    service = KnowledgeService(db_session, storage=storage)
    doc = await service.create_document(
        user_id=user_id,
        title=title,
        filename=filename,
        mime_type="text/plain",
        size_bytes=len(content),
        storage_key=storage_key,
    )
    await db_session.commit()

    task = BackgroundTask(
        id=str(uuid.uuid4()),
        user_id=user_id,
        task_type="knowledge_index",
        target_type="document",
        target_id=doc.id,
        status="pending",
    )
    db_session.add(task)
    await db_session.commit()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.services.storage.get_object_storage", lambda: storage)
        await _execute_knowledge_index(db_session, task)

    return doc.id


class TestKnowledgeDeleteCleanup:
    """Verify delete cleans up chunks and storage."""

    async def test_delete_marks_document_deleted(self, db_session):
        """Delete should set document status to 'deleted'."""
        storage = InMemoryObjectStorage()
        user_id = await _create_user(db_session, "kb-del-status")

        doc_id = await _create_ready_document(db_session, user_id, storage)

        service = KnowledgeService(db_session, storage=storage)
        await service.delete_document(doc_id, user_id)

        doc = await service.get_document(doc_id, user_id)
        assert doc.status == "deleted"

    async def test_delete_removes_chunks(self, db_session):
        """Delete should remove all chunks from DB."""
        storage = InMemoryObjectStorage()
        user_id = await _create_user(db_session, "kb-del-chunks")

        doc_id = await _create_ready_document(db_session, user_id, storage)

        # Verify chunks exist before delete
        result = await db_session.execute(select(KnowledgeChunk).where(KnowledgeChunk.document_id == doc_id))
        chunks_before = list(result.scalars().all())
        assert len(chunks_before) > 0

        service = KnowledgeService(db_session, storage=storage)
        await service.delete_document(doc_id, user_id)

        # Chunks should be deleted
        result = await db_session.execute(select(KnowledgeChunk).where(KnowledgeChunk.document_id == doc_id))
        chunks_after = list(result.scalars().all())
        assert len(chunks_after) == 0

    async def test_delete_removes_from_storage(self, db_session):
        """Delete should best-effort remove from object storage."""
        storage = InMemoryObjectStorage()
        user_id = await _create_user(db_session, "kb-del-storage")

        doc_id = await _create_ready_document(db_session, user_id, storage)

        service = KnowledgeService(db_session, storage=storage)
        doc = await service.get_document(doc_id, user_id)

        # Verify file exists in storage
        assert await storage.exists(doc.storage_key)

        await service.delete_document(doc_id, user_id)

        # File should be deleted from storage
        assert not await storage.exists(doc.storage_key)

    async def test_search_excludes_deleted_documents(self, db_session):
        """Search should not return results from deleted documents."""
        storage = InMemoryObjectStorage()
        user_id = await _create_user(db_session, "kb-del-search")

        doc_id = await _create_ready_document(
            db_session,
            user_id,
            storage,
            title="Deletable Doc",
            content=b"Unique searchable content for deletion test.",
        )

        # Search should find it
        service = KnowledgeService(db_session, storage=storage)
        results = await service.search(user_id=user_id, query="deletion")
        assert len(results) > 0

        # Delete the document
        await service.delete_document(doc_id, user_id)

        # Search should no longer find it
        results = await service.search(user_id=user_id, query="deletion")
        assert len(results) == 0

    async def test_delete_storage_failure_still_deletes_db(self, db_session):
        """If storage delete fails, DB record should still be marked deleted."""
        storage = InMemoryObjectStorage()
        user_id = await _create_user(db_session, "kb-del-fail")

        doc_id = await _create_ready_document(db_session, user_id, storage)

        # Make storage.delete raise an error
        original_delete = storage.delete

        async def failing_delete(key: str) -> None:
            raise RuntimeError("Storage unavailable")

        storage.delete = failing_delete

        service = KnowledgeService(db_session, storage=storage)
        # Should not raise — storage failure is best-effort
        await service.delete_document(doc_id, user_id)

        # DB record should still be marked deleted
        doc = await service.get_document(doc_id, user_id)
        assert doc.status == "deleted"

        # Chunks should still be cleaned from DB
        result = await db_session.execute(select(KnowledgeChunk).where(KnowledgeChunk.document_id == doc_id))
        assert len(list(result.scalars().all())) == 0

        # Restore for cleanup
        storage.delete = original_delete
