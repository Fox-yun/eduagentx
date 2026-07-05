"""Integration tests: Knowledge reindex doesn't break old version.

Verifies:
  - Reindex creates a new index_version
  - Old version chunks are deleted after activation
  - Search works after reindex
  - Reindex doesn't lose data (old content is replaced, not lost)

Run with:
    pytest tests/integration/test_knowledge_reindex.py -v
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.models.user import User
from app.services.knowledge import KnowledgeService
from app.services.storage import InMemoryObjectStorage


async def _create_user(db_session, prefix: str = "kb-reindex") -> str:
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


async def _upload_and_index(
    db_session,
    user_id: str,
    title: str,
    filename: str,
    content: bytes,
    storage: InMemoryObjectStorage,
) -> str:
    """Upload and index a document, returning doc_id."""
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


class TestKnowledgeReindex:
    """Verify reindex doesn't break old version."""

    async def test_reindex_creates_new_version(self, db_session):
        """Reindex should increment the index_version."""
        storage = InMemoryObjectStorage()
        user_id = await _create_user(db_session, "kb-reidx-ver")

        content = b"Original content about Python programming basics."
        doc_id = await _upload_and_index(db_session, user_id, "Python Basics", "basics.txt", content, storage)

        service = KnowledgeService(db_session, storage=storage)
        doc = await service.get_document(doc_id, user_id)
        assert doc.active_index_version == 1

        # Reindex with updated content
        storage._store[doc.storage_key] = b"Updated content about Python programming advanced topics."

        # Transition to reindexing
        doc.status = "reindexing"
        await db_session.commit()

        from app.models.task import BackgroundTask
        from app.workers.tasks import _execute_knowledge_index

        task = BackgroundTask(
            id=str(uuid.uuid4()),
            user_id=user_id,
            task_type="knowledge_reindex",
            target_type="document",
            target_id=doc_id,
            status="pending",
        )
        db_session.add(task)
        await db_session.commit()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.services.storage.get_object_storage", lambda: storage)
            await _execute_knowledge_index(db_session, task)

        # Verify new version
        await db_session.refresh(doc)
        assert doc.active_index_version == 2
        assert doc.status == "ready"

    async def test_reindex_old_chunks_deleted(self, db_session):
        """After reindex, old version chunks should be deleted."""
        from sqlalchemy import select

        from app.models.knowledge import KnowledgeChunk

        storage = InMemoryObjectStorage()
        user_id = await _create_user(db_session, "kb-reidx-del")

        content = b"Original content for testing reindex cleanup."
        doc_id = await _upload_and_index(db_session, user_id, "Reindex Test", "reindex.txt", content, storage)

        # Verify chunks exist for version 1
        result = await db_session.execute(
            select(KnowledgeChunk).where(
                KnowledgeChunk.document_id == doc_id,
                KnowledgeChunk.index_version == 1,
            )
        )
        v1_chunks = list(result.scalars().all())
        assert len(v1_chunks) > 0

        # Reindex with new content
        service = KnowledgeService(db_session, storage=storage)
        doc = await service.get_document(doc_id, user_id)
        storage._store[doc.storage_key] = b"Completely new content after reindex operation."
        doc.status = "reindexing"
        await db_session.commit()

        from app.models.task import BackgroundTask
        from app.workers.tasks import _execute_knowledge_index

        task = BackgroundTask(
            id=str(uuid.uuid4()),
            user_id=user_id,
            task_type="knowledge_reindex",
            target_type="document",
            target_id=doc_id,
            status="pending",
        )
        db_session.add(task)
        await db_session.commit()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.services.storage.get_object_storage", lambda: storage)
            await _execute_knowledge_index(db_session, task)

        # Old version chunks should be deleted
        result = await db_session.execute(
            select(KnowledgeChunk).where(
                KnowledgeChunk.document_id == doc_id,
                KnowledgeChunk.index_version == 1,
            )
        )
        old_chunks = list(result.scalars().all())
        assert len(old_chunks) == 0

        # New version chunks should exist
        result = await db_session.execute(
            select(KnowledgeChunk).where(
                KnowledgeChunk.document_id == doc_id,
                KnowledgeChunk.index_version == 2,
            )
        )
        new_chunks = list(result.scalars().all())
        assert len(new_chunks) > 0

    async def test_search_works_after_reindex(self, db_session):
        """Search should return results from the new version after reindex."""
        storage = InMemoryObjectStorage()
        user_id = await _create_user(db_session, "kb-reidx-search")

        content = b"Original content about database design and normalization."
        doc_id = await _upload_and_index(db_session, user_id, "DB Design", "db.txt", content, storage)

        # Verify search works
        service = KnowledgeService(db_session, storage=storage)
        results = await service.search(user_id=user_id, query="database")
        assert len(results) > 0

        # Reindex with new content
        doc = await service.get_document(doc_id, user_id)
        storage._store[doc.storage_key] = b"Updated content about network security protocols."
        doc.status = "reindexing"
        await db_session.commit()

        from app.models.task import BackgroundTask
        from app.workers.tasks import _execute_knowledge_index

        task = BackgroundTask(
            id=str(uuid.uuid4()),
            user_id=user_id,
            task_type="knowledge_reindex",
            target_type="document",
            target_id=doc_id,
            status="pending",
        )
        db_session.add(task)
        await db_session.commit()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.services.storage.get_object_storage", lambda: storage)
            await _execute_knowledge_index(db_session, task)

        # Search for old content — should not find it
        results = await service.search(user_id=user_id, query="database")
        assert len(results) == 0

        # Search for new content — should find it
        results = await service.search(user_id=user_id, query="network security")
        assert len(results) > 0
