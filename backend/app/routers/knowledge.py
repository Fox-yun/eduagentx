"""Knowledge base API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas import CursorPage
from app.core.auth_deps import require_learning_user
from app.core.database import get_db
from app.core.errors import ApiError
from app.models.user import User
from app.services.knowledge import KnowledgeService

router = APIRouter()


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
    """Upload a document to the knowledge base."""
    if not file.filename:
        raise ApiError(code="MISSING_FILENAME", message="Filename is required", status_code=400)

    # Determine MIME type
    mime_type = file.content_type or "application/octet-stream"

    # Read file content and check size
    content = await file.read()
    size_bytes = len(content)

    # Validate file size early
    from app.services.knowledge import MAX_FILE_SIZE

    if size_bytes > MAX_FILE_SIZE:
        raise ApiError(
            code="FILE_TOO_LARGE",
            message=f"File size exceeds maximum of {MAX_FILE_SIZE // (1024 * 1024)}MB",
            status_code=400,
        )

    # In production, would upload to object storage
    storage_key = f"knowledge/{user.id}/{file.filename}"

    service = KnowledgeService(db)
    doc = await service.create_document(
        user_id=user.id,
        title=file.filename,
        filename=file.filename,
        mime_type=mime_type,
        size_bytes=size_bytes,
        storage_key=storage_key,
    )

    # In production, would trigger indexing task
    return service._format_document(doc)


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
    """
    service = KnowledgeService(db)
    doc = await service.get_document(document_id, user.id)

    # Validate document can be reindexed
    if doc.status not in ("ready", "failed"):
        raise ApiError(
            code="INVALID_STATUS",
            message=f"Cannot reindex document in '{doc.status}' status",
            status_code=400,
        )

    # Update document status
    await service.update_document_status(document_id, "reindexing", operation_status="queued")

    # Create background task
    from app.services.task import TaskService

    task_service = TaskService(db)
    task = await task_service.create_task(
        user_id=user.id,
        task_type="knowledge_reindex",
        target_type="document",
        target_id=document_id,
    )

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
    """Search the knowledge base."""
    service = KnowledgeService(db)
    results = await service.search(user.id, q, limit)
    return {"results": results}
