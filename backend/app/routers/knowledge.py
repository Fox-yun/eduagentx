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

    # Read file content
    content = await file.read()
    size_bytes = len(content)

    # Determine MIME type
    mime_type = file.content_type or "application/octet-stream"

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
) -> dict[str, str]:
    """Reindex a document."""
    service = KnowledgeService(db)
    doc = await service.get_document(document_id, user.id)

    # In production, would trigger reindex task
    return {"message": "Reindex started", "document_id": doc.id}


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
