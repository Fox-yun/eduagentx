"""Integration tests: Knowledge storage failure handling.

Verifies:
  - MinIO failure during upload doesn't produce a ready document
  - Storage failure during indexing marks document as 'failed'
  - Storage unavailability is handled gracefully

Run with:
    pytest tests/integration/test_knowledge_storage_failure.py -v
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.models.user import User
from app.services.knowledge import KnowledgeService
from app.services.storage import InMemoryObjectStorage


async def _create_user(db_session, prefix: str = "kb-fail") -> str:
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


class FailingStorage(InMemoryObjectStorage):
    """Storage that fails on get() to simulate MinIO unavailability."""

    async def get(self, key: str) -> bytes:
        raise RuntimeError("MinIO connection refused")


class TestKnowledgeStorageFailure:
    """Verify storage failures are handled correctly."""

    async def test_storage_failure_during_indexing_marks_failed(self, db_session):
        """If storage fails during indexing, document should be marked 'failed'."""
        storage = InMemoryObjectStorage()
        user_id = await _create_user(db_session, "kb-fail-idx")

        # Upload content normally
        content = b"Content that will fail to be read during indexing."
        storage_key = f"knowledge/{user_id}/{uuid.uuid4()}_test.txt"
        await storage.put(storage_key, content, "text/plain")

        service = KnowledgeService(db_session, storage=storage)
        doc = await service.create_document(
            user_id=user_id,
            title="Fail Doc",
            filename="test.txt",
            mime_type="text/plain",
            size_bytes=len(content),
            storage_key=storage_key,
        )
        await db_session.commit()

        # Now make storage fail (simulate MinIO down during indexing)
        failing_storage = FailingStorage()
        # Copy existing data
        failing_storage._store = dict(storage._store)

        from app.models.task import BackgroundTask
        from app.workers.tasks import _execute_knowledge_index

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

        with pytest.raises(RuntimeError):
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr("app.services.storage.get_object_storage", lambda: failing_storage)
                await _execute_knowledge_index(db_session, task)

        # Document should be marked as failed
        await db_session.refresh(doc)
        assert doc.status == "failed"
        assert doc.error is not None

    async def test_storage_failure_does_not_produce_ready_document(self, db_session):
        """A failed indexing should never result in a 'ready' document."""
        storage = InMemoryObjectStorage()
        user_id = await _create_user(db_session, "kb-fail-ready")

        content = b"Content for failed indexing test."
        storage_key = f"knowledge/{user_id}/{uuid.uuid4()}_fail.txt"
        await storage.put(storage_key, content, "text/plain")

        service = KnowledgeService(db_session, storage=storage)
        doc = await service.create_document(
            user_id=user_id,
            title="Fail Ready Test",
            filename="fail.txt",
            mime_type="text/plain",
            size_bytes=len(content),
            storage_key=storage_key,
        )
        await db_session.commit()

        # Use failing storage for indexing
        failing_storage = FailingStorage()
        failing_storage._store = dict(storage._store)

        from app.models.task import BackgroundTask
        from app.workers.tasks import _execute_knowledge_index

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

        with pytest.raises(RuntimeError):
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr("app.services.storage.get_object_storage", lambda: failing_storage)
                await _execute_knowledge_index(db_session, task)

        await db_session.refresh(doc)
        # Must NOT be ready
        assert doc.status != "ready"
        assert doc.status == "failed"

        # Search should return no results
        results = await service.search(user_id=user_id, query="content")
        assert len(results) == 0

    async def test_empty_document_produces_no_chunks(self, db_session):
        """An empty document should fail indexing, not produce ready status."""
        storage = InMemoryObjectStorage()
        user_id = await _create_user(db_session, "kb-fail-empty")

        content = b""  # Empty file
        storage_key = f"knowledge/{user_id}/{uuid.uuid4()}_empty.txt"
        await storage.put(storage_key, content, "text/plain")

        service = KnowledgeService(db_session, storage=storage)
        doc = await service.create_document(
            user_id=user_id,
            title="Empty Doc",
            filename="empty.txt",
            mime_type="text/plain",
            size_bytes=0,
            storage_key=storage_key,
        )
        await db_session.commit()

        from app.models.task import BackgroundTask
        from app.workers.tasks import _execute_knowledge_index

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

        # Should raise because no parseable content
        with pytest.raises((ValueError, RuntimeError)):
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr("app.services.storage.get_object_storage", lambda: storage)
                await _execute_knowledge_index(db_session, task)

        await db_session.refresh(doc)
        assert doc.status == "failed"
