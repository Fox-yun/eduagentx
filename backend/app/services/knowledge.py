"""Knowledge base service for document management and RAG."""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.datetime import to_iso_string
from app.core.errors import ApiError
from app.core.pagination import decode_cursor, encode_cursor
from app.models.knowledge import (
    KnowledgeChunk,
    KnowledgeDocument,
    validate_document_transition,
)

logger = structlog.get_logger()

# Allowed MIME types
ALLOWED_MIME_TYPES: frozenset[str] = frozenset(
    {
        "application/pdf",
        "text/plain",
        "text/markdown",
        "text/csv",
        "application/json",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
)

# Max file size: 50MB
MAX_FILE_SIZE = 50 * 1024 * 1024


class KnowledgeService:
    """Knowledge base business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_document(
        self,
        user_id: str,
        title: str,
        filename: str,
        mime_type: str,
        size_bytes: int,
        storage_key: str,
        scope: str = "personal",
        checksum: str | None = None,
    ) -> KnowledgeDocument:
        """Create a new knowledge document."""
        # Validate MIME type
        if mime_type not in ALLOWED_MIME_TYPES:
            raise ApiError(
                code="INVALID_MIME_TYPE",
                message=f"File type '{mime_type}' is not allowed",
                status_code=400,
            )

        # Validate size
        if size_bytes > MAX_FILE_SIZE:
            raise ApiError(
                code="FILE_TOO_LARGE",
                message=f"File size exceeds maximum of {MAX_FILE_SIZE // (1024 * 1024)}MB",
                status_code=400,
            )

        doc = KnowledgeDocument(
            id=str(uuid.uuid4()),
            user_id=user_id,
            scope=scope,
            title=title,
            filename=filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            storage_key=storage_key,
            status="uploaded",
            operation_status="idle",
            checksum=checksum,
        )
        self.db.add(doc)
        await self.db.flush()
        return doc

    async def get_document(
        self,
        document_id: str,
        user_id: str,
    ) -> KnowledgeDocument:
        """Get a document by ID, ensuring ownership."""
        result = await self.db.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.user_id == user_id,
            )
        )
        doc = result.scalar_one_or_none()
        if not doc:
            raise ApiError(code="DOCUMENT_NOT_FOUND", message="Document not found", status_code=404)
        return doc

    async def list_documents(
        self,
        user_id: str,
        cursor: str | None = None,
        limit: int = 20,
    ) -> dict:
        """List documents for a user with cursor pagination."""
        if limit < 1 or limit > 100:
            limit = 20

        query = select(KnowledgeDocument).where(
            KnowledgeDocument.user_id == user_id,
            KnowledgeDocument.status != "deleted",
        )

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply cursor
        if cursor:
            cursor_data = decode_cursor(cursor)
            cursor_created = cursor_data.get("order")
            cursor_id = cursor_data.get("id")
            if cursor_created and cursor_id:
                query = query.where(
                    (KnowledgeDocument.created_at < cursor_created)
                    | ((KnowledgeDocument.created_at == cursor_created) & (KnowledgeDocument.id < cursor_id))
                )

        query = query.order_by(KnowledgeDocument.created_at.desc(), KnowledgeDocument.id.desc())
        query = query.limit(limit + 1)

        result = await self.db.execute(query)
        docs = list(result.scalars().all())

        has_next = len(docs) > limit
        if has_next:
            docs = docs[:limit]
            last = docs[-1]
            next_cursor = encode_cursor(
                {
                    "order": str(last.created_at),
                    "id": last.id,
                }
            )
        else:
            next_cursor = None

        return {
            "items": docs,
            "next_cursor": next_cursor,
            "total": total,
        }

    async def delete_document(
        self,
        document_id: str,
        user_id: str,
    ) -> None:
        """Soft delete a document."""
        doc = await self.get_document(document_id, user_id)

        if not validate_document_transition(doc.status, "deleted"):
            raise ApiError(
                code="INVALID_STATUS",
                message=f"Cannot delete document in '{doc.status}' status",
                status_code=400,
            )

        doc.status = "deleted"
        doc.operation_status = "idle"
        await self.db.flush()

    async def update_document_status(
        self,
        document_id: str,
        target_status: str,
        operation_status: str | None = None,
        error: str | None = None,
    ) -> KnowledgeDocument:
        """Update document status."""
        result = await self.db.execute(select(KnowledgeDocument).where(KnowledgeDocument.id == document_id))
        doc = result.scalar_one_or_none()
        if not doc:
            raise ApiError(code="DOCUMENT_NOT_FOUND", message="Document not found", status_code=404)

        if not validate_document_transition(doc.status, target_status):
            raise ApiError(
                code="INVALID_TRANSITION",
                message=f"Cannot transition from '{doc.status}' to '{target_status}'",
                status_code=400,
            )

        doc.status = target_status
        if operation_status:
            doc.operation_status = operation_status
        if error:
            doc.error = error

        await self.db.flush()
        return doc

    async def add_chunks(
        self,
        document_id: str,
        chunks: list[dict],
    ) -> list[KnowledgeChunk]:
        """Add chunks to a document."""
        result = await self.db.execute(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == document_id)
            .order_by(KnowledgeChunk.chunk_index.desc())
            .limit(1)
        )
        last_chunk = result.scalar_one_or_none()
        start_index = (last_chunk.chunk_index + 1) if last_chunk else 0

        created_chunks = []
        for i, chunk_data in enumerate(chunks):
            chunk = KnowledgeChunk(
                id=str(uuid.uuid4()),
                document_id=document_id,
                chunk_index=start_index + i,
                content=chunk_data["content"],
                token_count=chunk_data.get("token_count", 0),
                page_number=chunk_data.get("page_number"),
                section_title=chunk_data.get("section_title"),
                embedding=chunk_data.get("embedding"),
                metadata=chunk_data.get("metadata"),
            )
            self.db.add(chunk)
            created_chunks.append(chunk)

        await self.db.flush()
        return created_chunks

    async def search(
        self,
        user_id: str,
        query: str,
        limit: int = 10,
        scope: str | None = None,
    ) -> list[dict]:
        """Search knowledge base using text matching.

        In production, this would use vector similarity search with pgvector.
        For now, we use simple text matching.
        """
        if limit < 1 or limit > 50:
            limit = 10

        # Build query for accessible documents
        doc_query = select(KnowledgeDocument.id).where(
            KnowledgeDocument.user_id == user_id,
            KnowledgeDocument.status == "ready",
        )
        if scope:
            doc_query = doc_query.where(KnowledgeDocument.scope == scope)

        doc_result = await self.db.execute(doc_query)
        doc_ids = [row[0] for row in doc_result.all()]

        if not doc_ids:
            return []

        # Search chunks
        chunk_query = (
            select(KnowledgeChunk)
            .where(
                KnowledgeChunk.document_id.in_(doc_ids),
                KnowledgeChunk.content.ilike(f"%{query.replace('%', '\\%').replace('_', '\\_')}%"),
            )
            .limit(limit)
        )

        result = await self.db.execute(chunk_query)
        chunks = list(result.scalars().all())

        return [
            {
                "id": chunk.id,
                "file_name": "",  # Would be populated from document
                "text": chunk.content,
                "score": 0.5,  # Placeholder score
            }
            for chunk in chunks
        ]

    def _format_document(self, doc: KnowledgeDocument) -> dict:
        """Format document for API response."""
        # Map internal status to frontend enum
        status_map = {
            "uploaded": "pending",
            "scanning": "pending",
            "parsing": "pending",
            "chunking": "pending",
            "embedding": "pending",
            "ready": "indexed",
            "reindexing": "indexing",
            "failed": "failed",
            "deleted": "failed",
        }
        # Map operation_status to frontend enum
        op_status_map = {
            "idle": "ready",
            "uploading": "uploading",
            "uploaded": "uploaded",
            "queued": "queued",
            "parsing": "parsing",
            "chunking": "chunking",
            "indexing": "indexing",
            "reindexing": "reindexing",
            "ready": "ready",
            "failed": "failed",
            "deleting": "deleting",
            "delete_failed": "delete_failed",
        }

        return {
            "document_id": doc.id,
            "display_name": doc.title,
            "scope": doc.scope,
            "course_id": None,
            "mime_type": doc.mime_type,
            "size_bytes": doc.size_bytes,
            "status": status_map.get(doc.status, "pending"),
            "operation_status": op_status_map.get(doc.operation_status, "ready"),
            "index_task_id": doc.index_task_id,
            "error": doc.error,
            "created_at": to_iso_string(doc.created_at),
            "updated_at": to_iso_string(doc.updated_at),
        }
