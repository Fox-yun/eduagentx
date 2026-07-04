"""Tutor service — real-time Q&A for learning nodes with RAG."""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.unit import LearningUnitContent
from app.prompts.agents import TUTOR_SYSTEM, tutor_context
from app.services.knowledge import KnowledgeService
from app.services.learning_access import require_node_access
from app.services.llm import LLMError, llm_chat

logger = structlog.get_logger()

# Maximum characters of knowledge context to inject into the prompt.
# ~4 chars ≈ 1 token, so 6000 chars ≈ ~1500 tokens of knowledge context.
_MAX_KNOWLEDGE_CONTEXT_CHARS = 6000

# Top-K chunks to retrieve from the knowledge base.
_KNOWLEDGE_TOP_K = 5


class TutorService:
    """Answer student questions about a learning node using LLM + RAG."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def ask(
        self,
        path_id: str,
        node_id: str,
        user_id: str,
        question: str,
    ) -> dict[str, Any]:
        """Answer a student's question about a specific learning node.

        Flow:
          1. Verify Path/Node access.
          2. Fetch Unit Content for base context.
          3. Knowledge Search Top-K (user's own documents only).
          4. Build token-limited context.
          5. Call LLM.
          6. Return Answer + Citations.

        Never leaks internal errors to the user.
        """
        # 1. Access control — verify user owns the path and node belongs to active version
        try:
            ctx = await require_node_access(self.db, user_id, path_id, node_id)
        except Exception:
            logger.warning("tutor_access_denied", path_id=path_id, node_id=node_id, user_id=user_id)
            raise

        node_title = ctx.node.title or "未知节点"

        # 2. Look up unit content for richer context
        content_result = await self.db.execute(
            select(LearningUnitContent).where(
                LearningUnitContent.path_id == path_id,
                LearningUnitContent.node_id == node_id,
                LearningUnitContent.user_id == user_id,
            )
        )
        content = content_result.scalar_one_or_none()

        # 3. Build unit content string
        node_content = ""
        if content and content.content:
            sections = content.content.get("sections", [])
            if sections:
                node_content = "\n\n".join(
                    f"### {s.get('title', '')}\n{s.get('content', '')[:500]}" for s in sections[:3]
                )

        # 4. Knowledge search (RAG) — best-effort, failures don't block answering
        knowledge_context = ""
        citations: list[dict[str, Any]] = []
        try:
            knowledge_context, citations = await self._build_knowledge_context(
                user_id=user_id,
                question=question,
            )
        except Exception as e:
            logger.warning("tutor_knowledge_search_failed", error=str(e), user_id=user_id)

        # 5. Build final context and call LLM
        context = tutor_context(
            node_title=node_title,
            node_content=node_content,
            knowledge_context=knowledge_context,
        )
        system = TUTOR_SYSTEM.format(context=context)

        try:
            answer = await llm_chat(
                system_prompt=system,
                user_message=question,
                temperature=0.6,
                max_tokens=2048,
            )
            return {
                "question": question,
                "answer": answer,
                "node_id": node_id,
                "citations": citations,
            }
        except LLMError as e:
            logger.error(
                "tutor_llm_error",
                error_type=type(e).__name__,
                request_id=getattr(e, "request_id", None),
                latency_ms=getattr(e, "latency_ms", None),
            )
            return {
                "question": question,
                "answer": "辅导服务暂时不可用，请稍后重试。",
                "node_id": node_id,
                "citations": [],
            }

    async def _build_knowledge_context(
        self,
        user_id: str,
        question: str,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Search the knowledge base and build a token-limited context string.

        Returns a tuple of ``(knowledge_context, citations)`` where
        *knowledge_context* is a numbered string suitable for the LLM prompt
        and *citations* is a list of metadata dicts for the API response.
        """
        ks = KnowledgeService(self.db)
        results = await ks.search(
            user_id=user_id,
            query=question,
            limit=_KNOWLEDGE_TOP_K,
        )

        if not results:
            return "", []

        # Build numbered context with token budget
        parts: list[str] = []
        citations: list[dict[str, Any]] = []
        total_chars = 0

        for idx, chunk in enumerate(results, start=1):
            chunk_text = chunk.get("text", "")
            chunk_id = chunk.get("id", "")
            document_id = chunk.get("document_id", "")
            file_name = chunk.get("file_name", "")
            page_number = chunk.get("page_number")
            section_title = chunk.get("section_title")

            # Stop if we'd exceed the budget
            entry = f"[{idx}] {chunk_text}"
            if total_chars + len(entry) > _MAX_KNOWLEDGE_CONTEXT_CHARS:
                break

            parts.append(entry)
            total_chars += len(entry)

            citation: dict[str, Any] = {
                "index": idx,
                "chunk_id": chunk_id,
                "document_id": document_id,
                "file_name": file_name,
            }
            if page_number is not None:
                citation["page_number"] = page_number
            if section_title:
                citation["section_title"] = section_title
            citations.append(citation)

        return "\n\n".join(parts), citations
