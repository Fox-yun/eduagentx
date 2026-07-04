"""Knowledge base service for document management and RAG."""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.datetime import to_iso_string
from app.core.errors import ApiError
from app.core.pagination import decode_cursor, encode_cursor
from app.models.knowledge import (
    KnowledgeChunk,
    KnowledgeDocument,
    validate_document_transition,
)
from app.services.storage import ObjectStorage, get_object_storage

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

    def __init__(self, db: AsyncSession, storage: ObjectStorage | None = None) -> None:
        self.db = db
        self._storage = storage

    @property
    def storage(self) -> ObjectStorage:
        if self._storage is None:
            self._storage = get_object_storage()
        return self._storage

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
    ) -> dict[str, Any]:
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
        """Delete a document: mark as deleted + remove object storage file.

        Object storage deletion is best-effort — if it fails, the document
        is still marked as deleted (the DB record is the source of truth).
        """
        doc = await self.get_document(document_id, user_id)

        if not validate_document_transition(doc.status, "deleted"):
            raise ApiError(
                code="INVALID_STATUS",
                message=f"Cannot delete document in '{doc.status}' status",
                status_code=400,
            )

        # Best-effort: delete from object storage
        try:
            await self.storage.delete(doc.storage_key)
        except Exception as e:
            logger.warning("storage_delete_failed", key=doc.storage_key, error=str(e))

        # Delete chunks from DB
        await self.db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id))

        doc.status = "deleted"
        doc.operation_status = "idle"
        doc.active_index_version = None
        await self.db.flush()
        await self.db.commit()

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
        chunks: list[dict[str, Any]],
        index_version: int = 1,
    ) -> list[KnowledgeChunk]:
        """Add chunks to a document with a specific index_version.

        Chunks are added with their content_hash and a generated tsvector
        for PostgreSQL full-text search.
        """
        created_chunks: list[KnowledgeChunk] = []
        for chunk_data in chunks:
            chunk = KnowledgeChunk(
                id=str(uuid.uuid4()),
                document_id=document_id,
                chunk_index=chunk_data["chunk_index"],
                content=chunk_data["content"],
                token_count=chunk_data.get("token_count", 0),
                page_number=chunk_data.get("page_number"),
                section_title=chunk_data.get("section_title"),
                content_hash=chunk_data.get("content_hash"),
                index_version=index_version,
            )
            self.db.add(chunk)
            created_chunks.append(chunk)

        await self.db.flush()

        # tsv is auto-populated by a PostgreSQL trigger (knowledge_chunks_tsv_update)
        # which fires BEFORE INSERT and sets tsv = to_tsvector('simple', content)
        return created_chunks

    async def delete_chunks_by_version(
        self,
        document_id: str,
        index_version: int,
    ) -> int:
        """Delete all chunks for a document with the given index_version."""
        result = await self.db.execute(
            delete(KnowledgeChunk)
            .where(
                KnowledgeChunk.document_id == document_id,
                KnowledgeChunk.index_version == index_version,
            )
            .returning(KnowledgeChunk.id)
        )
        deleted = result.fetchall()
        await self.db.flush()
        return len(deleted)

    async def activate_version(
        self,
        document_id: str,
        index_version: int,
    ) -> None:
        """Set the active_index_version on a document.

        This should be called AFTER new chunks are successfully created.
        Old chunks from previous versions are then deleted.
        """
        result = await self.db.execute(select(KnowledgeDocument).where(KnowledgeDocument.id == document_id))
        doc = result.scalar_one_or_none()
        if not doc:
            raise ApiError(code="DOCUMENT_NOT_FOUND", message="Document not found", status_code=404)

        old_version = doc.active_index_version
        doc.active_index_version = index_version
        await self.db.flush()

        # Delete old version chunks if they exist
        if old_version is not None and old_version != index_version:
            await self.db.execute(
                delete(KnowledgeChunk).where(
                    KnowledgeChunk.document_id == document_id,
                    KnowledgeChunk.index_version == old_version,
                )
            )
            await self.db.flush()

    async def search(
        self,
        user_id: str,
        query: str,
        limit: int = 10,
        scope: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search knowledge base using PostgreSQL full-text search.

        Uses plainto_tsquery for safe user input and ts_rank_cd for scoring.
        """
        if limit < 1 or limit > 50:
            limit = 10

        # Escape query for tsquery
        sanitized = query.strip()
        if not sanitized:
            return []

        # Build query for accessible documents (only ready docs)
        doc_query = select(KnowledgeDocument.id, KnowledgeDocument.title).where(
            KnowledgeDocument.user_id == user_id,
            KnowledgeDocument.status == "ready",
        )
        if scope:
            doc_query = doc_query.where(KnowledgeDocument.scope == scope)

        doc_result = await self.db.execute(doc_query)
        doc_rows = doc_result.all()

        if not doc_rows:
            return []

        doc_id_to_title: dict[str, str] = {row[0]: row[1] for row in doc_rows}
        doc_ids = list(doc_id_to_title.keys())

        # Full-text search using PostgreSQL ts_rank_cd
        # Use plainto_tsquery for safe, natural language query
        fts_query = text(
            """
            SELECT c.id, c.document_id, c.content, c.page_number, c.section_title,
                   ts_rank_cd(c.tsv, plainto_tsquery('simple', :q)) AS score
            FROM knowledge_chunks c
            WHERE c.document_id = ANY(:doc_ids)
              AND c.tsv @@ plainto_tsquery('simple', :q)
              AND c.index_version = (
                  SELECT d.active_index_version
                  FROM knowledge_documents d
                  WHERE d.id = c.document_id
              )
            ORDER BY score DESC
            LIMIT :limit
            """
        )

        result = await self.db.execute(
            fts_query,
            {
                "q": sanitized,
                "doc_ids": doc_ids,
                "limit": limit,
            },
        )
        rows = result.fetchall()

        return [
            {
                "id": row[0],
                "document_id": row[1],
                "file_name": doc_id_to_title.get(row[1], ""),
                "text": row[2],
                "score": float(row[5]),
                "page_number": row[3],
                "section_title": row[4],
            }
            for row in rows
        ]

    async def get_document_content(self, doc: KnowledgeDocument) -> bytes:
        """Download document content from object storage."""
        return await self.storage.get(doc.storage_key)

    def _format_document(self, doc: KnowledgeDocument) -> dict[str, Any]:
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
