"""Tutor service — real-time Q&A for learning nodes."""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.unit import LearningUnitContent
from app.prompts.agents import TUTOR_SYSTEM, tutor_context
from app.services.learning_access import require_node_access
from app.services.llm import LLMError, llm_chat

logger = structlog.get_logger()


class TutorService:
    """Answer student questions about a learning node using LLM."""

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

        Verifies access control before answering.
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

        # 3. Build context string
        node_content = ""
        if content and content.content:
            sections = content.content.get("sections", [])
            if sections:
                node_content = "\n\n".join(
                    f"### {s.get('title', '')}\n{s.get('content', '')[:500]}" for s in sections[:3]
                )

        context = tutor_context(node_title, node_content)
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
            }
