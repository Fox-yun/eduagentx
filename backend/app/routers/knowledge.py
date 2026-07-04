"""Knowledge base API endpoints."""

from __future__ import annotations

import hashlib
import uuid
from contextlib import suppress
from typing import Any

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas import CursorPage
from app.core.auth_deps import require_learning_user
from app.core.database import get_db
from app.core.errors import ApiError
from app.models.user import User
from app.services.knowledge import MAX_FILE_SIZE, KnowledgeService
from app.services.storage import get_object_storage

router = APIRouter()

# Chunk size for streaming read: 1MB
CHUNK_SIZE = 1024 * 1024


@router.get("/documents", response_model=CursorPage[dict[str, Any]])
async def list_documents(
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> CursorPage[dict[str, Any]]:
    """List knowledge documents with cursor pagination."""
    service = KnowledgeService(db)
    result = await service.list_documents(user.id, cursor, limit)

    return CursorPage(
        items=[service._format_document(d) for d in result["items"]],
        next_cursor=result["next_cursor"],
        total=result["total"],
    )


@router.post("/documents")
async def upload_document(
    file: UploadFile = File(...),
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Upload a document to the knowledge base.

    Streams the file to object storage while computing SHA-256 checksum.
    Creates a DB record only after successful upload.
    Triggers a background indexing task.
    """
    if not file.filename:
        raise ApiError(code="MISSING_FILENAME", message="Filename is required", status_code=400)

    mime_type = file.content_type or "application/octet-stream"

    storage = get_object_storage()
    service = KnowledgeService(db, storage=storage)

    # Generate UUID-based storage key
    storage_key = f"knowledge/{user.id}/{uuid.uuid4()}_{file.filename}"

    # Stream read: compute checksum + upload
    hasher = hashlib.sha256()
    total_size = 0
    file_content = bytearray()

    while True:
        chunk = await file.read(CHUNK_SIZE)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > MAX_FILE_SIZE:
            raise ApiError(
                code="FILE_TOO_LARGE",
                message=f"File size exceeds maximum of {MAX_FILE_SIZE // (1024 * 1024)}MB",
                status_code=400,
            )
        hasher.update(chunk)
        file_content.extend(chunk)

    if total_size == 0:
        raise ApiError(code="EMPTY_FILE", message="File is empty", status_code=400)

    checksum = hasher.hexdigest()
    content_bytes = bytes(file_content)

    # Upload to object storage
    await storage.put(storage_key, content_bytes, content_type=mime_type)

    # Create DB record (storage upload already succeeded)
    try:
        doc = await service.create_document(
            user_id=user.id,
            title=file.filename,
            filename=file.filename,
            mime_type=mime_type,
            size_bytes=total_size,
            storage_key=storage_key,
            checksum=checksum,
        )

        # Create indexing task
        from app.services.task import TaskService

        task_service = TaskService(db)
        task = await task_service.create_task(
            user_id=user.id,
            task_type="knowledge_index",
            target_type="document",
            target_id=doc.id,
        )

        doc.index_task_id = task.id
        doc.operation_status = "queued"
        await db.commit()
    except Exception:
        # Rollback: delete the uploaded object from storage
        with suppress(Exception):
            await storage.delete(storage_key)
        raise

    # Re-fetch from DB to ensure all server-generated columns
    # (created_at, updated_at) are loaded — avoids MissingGreenlet
    # when _format_document accesses them synchronously.
    fresh_doc = await service.get_document(doc.id, user.id)
    return service._format_document(fresh_doc)


@router.get("/documents/{document_id}")
async def get_document(
    document_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get a specific document."""
    service = KnowledgeService(db)
    doc = await service.get_document(document_id, user.id)
    return service._format_document(doc)


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Delete a document."""
    service = KnowledgeService(db)
    await service.delete_document(document_id, user.id)
    return {"message": "Document deleted"}


@router.post("/documents/{document_id}/reindex")
async def reindex_document(
    document_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Reindex a document.

    Creates a background task for reindexing and updates document status.
    The reindex uses version-based logic: new chunks are created with a
    new version number, and old chunks are deleted only after success.
    """
    service = KnowledgeService(db)
    doc = await service.get_document(document_id, user.id)

    if doc.status not in ("ready", "failed"):
        raise ApiError(
            code="INVALID_STATUS",
            message=f"Cannot reindex document in '{doc.status}' status",
            status_code=400,
        )

    await service.update_document_status(document_id, "reindexing", operation_status="queued")

    from app.services.task import TaskService

    task_service = TaskService(db)
    task = await task_service.create_task(
        user_id=user.id,
        task_type="knowledge_reindex",
        target_type="document",
        target_id=document_id,
    )

    doc.index_task_id = task.id
    await db.commit()

    return {
        "message": "Reindex started",
        "document_id": doc.id,
        "task_id": task.id,
    }


@router.get("/search")
async def search_knowledge(
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=50),
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Search the knowledge base using PostgreSQL full-text search."""
    service = KnowledgeService(db)
    results = await service.search(user.id, q, limit)
    return {"results": results}
