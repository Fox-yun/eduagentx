"""Tutor service — real-time Q&A for learning nodes."""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.path import LearningNode
from app.models.unit import LearningUnitContent
from app.prompts.agents import TUTOR_SYSTEM, tutor_context
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
        """Answer a student's question about a specific learning node."""
        # Look up node context
        node_result = await self.db.execute(select(LearningNode).where(LearningNode.id == node_id))
        node = node_result.scalar_one_or_none()
        node_title = node.title if node else "未知节点"

        # Look up unit content for richer context
        content_result = await self.db.execute(
            select(LearningUnitContent).where(
                LearningUnitContent.path_id == path_id,
                LearningUnitContent.node_id == node_id,
                LearningUnitContent.user_id == user_id,
            )
        )
        content = content_result.scalar_one_or_none()

        # Build context string
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
            logger.error("tutor_llm_error", error=str(e))
            return {
                "question": question,
                "answer": f"抱歉，辅导智能体暂时无法回答。错误信息：{e}",
                "node_id": node_id,
            }
