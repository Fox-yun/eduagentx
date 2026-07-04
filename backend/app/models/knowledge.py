"""Knowledge base models for document storage and RAG."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

if TYPE_CHECKING:
    from datetime import datetime


def generate_uuid() -> str:
    return str(uuid.uuid4())


class KnowledgeDocument(Base):
    """A document in the knowledge base."""

    __tablename__ = "knowledge_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="personal")
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="uploaded", index=True)
    operation_status: Mapped[str] = mapped_column(String(20), nullable=False, default="idle")
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    extra_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    index_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    active_index_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class KnowledgeChunk(Base):
    """A chunk of content from a knowledge document."""

    __tablename__ = "knowledge_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_documents.id"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    index_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tsv: Mapped[Any] = mapped_column(TSVECTOR, nullable=True)
    extra_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class KnowledgeSearchResult:
    """Represents a search result from the knowledge base."""

    def __init__(
        self,
        chunk_id: str,
        document_id: str,
        content: str,
        score: float,
        page_number: int | None = None,
        section_title: str | None = None,
    ):
        self.chunk_id = chunk_id
        self.document_id = document_id
        self.content = content
        self.score = score
        self.page_number = page_number
        self.section_title = section_title


# Document status transitions
DOCUMENT_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "uploaded": {"scanning", "failed", "deleted"},
    "scanning": {"parsing", "failed"},
    "parsing": {"chunking", "failed"},
    "chunking": {"embedding", "failed"},
    "embedding": {"ready", "failed"},
    "ready": {"reindexing", "deleted"},
    "reindexing": {"ready", "failed"},
    "failed": {"reindexing", "deleted"},
    "deleted": set(),
}


def validate_document_transition(current: str, target: str) -> bool:
    """Validate a document status transition."""
    allowed = DOCUMENT_STATUS_TRANSITIONS.get(current, set())
    return target in allowed
