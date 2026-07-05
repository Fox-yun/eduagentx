"""RAG Context Builder — structured retrieval-augmented generation context.

Provides a safe, structured interface for downstream modules (Tutor, content
generation, assessment) to retrieve knowledge base chunks and format them
for LLM consumption.

Contract guarantees:
  - Never outputs internal storage keys
  - Never outputs raw private paths
  - Never outputs unfiltered prompts
  - Only structured chunks, citations, document titles, and confidence
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.knowledge import KnowledgeService

logger = structlog.get_logger()

# Maximum characters of knowledge context to inject into prompts.
# ~4 chars ≈ 1 token, so 6000 chars ≈ ~1500 tokens of knowledge context.
_MAX_CONTEXT_CHARS = 6000

# Default top-K chunks to retrieve.
_DEFAULT_TOP_K = 5


@dataclass(frozen=True)
class Citation:
    """A single citation referencing a knowledge base chunk."""

    index: int
    chunk_id: str
    document_id: str
    document_title: str
    page_number: int | None = None
    section_title: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a safe dict for API responses (no internal keys)."""
        result: dict[str, Any] = {
            "index": self.index,
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "file_name": self.document_title,
        }
        if self.page_number is not None:
            result["page_number"] = self.page_number
        if self.section_title:
            result["section_title"] = self.section_title
        return result


@dataclass(frozen=True)
class RagContext:
    """Structured RAG context for downstream LLM consumption.

    Contains:
      - chunks: The retrieved text chunks (safe, no internal keys)
      - citations: Metadata for API response (safe for frontend)
      - document_titles: Unique list of source document titles
      - confidence: RAG confidence score (0.0 if no results)
      - context_string: Formatted string for LLM prompt injection

    Guarantees:
      - No internal storage keys
      - No raw private paths
      - No unfiltered prompt text
    """

    chunks: tuple[str, ...]
    citations: tuple[Citation, ...]
    document_titles: tuple[str, ...]
    confidence: float
    context_string: str

    @property
    def has_results(self) -> bool:
        """True if knowledge base returned any results."""
        return len(self.chunks) > 0

    def to_prompt_section(self) -> str:
        """Return the context string for LLM prompt injection.

        If no results, returns an empty string (downstream modules
        should handle this gracefully).
        """
        return self.context_string


async def build_rag_context(
    db: AsyncSession,
    *,
    user_id: str,
    query: str,
    path_id: str | None = None,
    node_id: str | None = None,
    limit: int = _DEFAULT_TOP_K,
) -> RagContext:
    """Build a structured RAG context from the knowledge base.

    Searches the user's knowledge base for chunks matching the query,
    then formats them into a safe, structured context for LLM consumption.

    Args:
        db: Database session
        user_id: The user ID (for knowledge base access control)
        query: The search query (natural language)
        path_id: Optional path ID for context (currently unused but reserved)
        node_id: Optional node ID for context (currently unused but reserved)
        limit: Maximum number of chunks to retrieve

    Returns:
        RagContext with safe, structured chunks and citations.
        If no results, returns an empty RagContext with confidence=0.0.

    Guarantees:
        - No internal storage keys in output
        - No raw private paths in output
        - No unfiltered prompt text in output
    """
    if limit < 1 or limit > 20:
        limit = _DEFAULT_TOP_K

    # Search the knowledge base (best-effort)
    try:
        service = KnowledgeService(db)
        results = await service.search(
            user_id=user_id,
            query=query,
            limit=limit,
        )
    except Exception as e:
        logger.warning("rag_context_search_failed", error=str(e), user_id=user_id)
        return RagContext(
            chunks=(),
            citations=(),
            document_titles=(),
            confidence=0.0,
            context_string="",
        )

    if not results:
        return RagContext(
            chunks=(),
            citations=(),
            document_titles=(),
            confidence=0.0,
            context_string="",
        )

    # Build structured output
    chunks_list: list[str] = []
    citations_list: list[Citation] = []
    document_titles_set: set[str] = set()
    total_score = 0.0
    total_chars = 0

    for idx, chunk in enumerate(results, start=1):
        chunk_text = chunk.get("text", "")
        chunk_id = chunk.get("id", "")
        document_id = chunk.get("document_id", "")
        document_title = chunk.get("file_name", "")
        page_number = chunk.get("page_number")
        section_title = chunk.get("section_title")
        score = float(chunk.get("score", 0.0))

        # Stop if we'd exceed the character budget
        entry = f"[{idx}] {chunk_text}"
        if total_chars + len(entry) > _MAX_CONTEXT_CHARS:
            break

        chunks_list.append(chunk_text)
        document_titles_set.add(document_title)
        total_score += score
        total_chars += len(entry)

        citations_list.append(
            Citation(
                index=idx,
                chunk_id=chunk_id,
                document_id=document_id,
                document_title=document_title,
                page_number=page_number,
                section_title=section_title,
            )
        )

    # Build context string for LLM prompt
    parts = [f"[{i + 1}] {text}" for i, text in enumerate(chunks_list)]
    context_string = "\n\n".join(parts)

    # Confidence: average score of retrieved chunks (normalized to 0-1)
    confidence = total_score / len(results) if results else 0.0

    return RagContext(
        chunks=tuple(chunks_list),
        citations=tuple(citations_list),
        document_titles=tuple(document_titles_set),
        confidence=confidence,
        context_string=context_string,
    )
