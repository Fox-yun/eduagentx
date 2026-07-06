"""Profile conversation service — conversational 8-dimensional profile extraction.

Phase 3.6-B: Handles multi-turn conversation for extracting learner profile
dimensions via LLM, with rule-based fallback when LLM is unavailable.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import (
    PROFILE_DIMENSIONS,
    ProfileConversationStatus,
    ProfileEvidenceType,
    ProfileMessageRole,
)
from app.models.profile import ProfileConversationMessage, ProfileConversationSession, StudentProfile
from app.models.user import StudentProfileEvidence
from app.prompts.profile import (
    FALLBACK_QUESTIONS,
    PROFILE_CONVERSATION_SYSTEM,
    build_initial_question,
    build_profile_conversation_user_message,
)
from app.services.llm import LLMError, llm_json

logger = structlog.get_logger()

# Conversation policy constants
MIN_TURNS = 3
MAX_TURNS = 7
MIN_DIMENSIONS_COVERED = 6
MIN_AVG_CONFIDENCE = 0.65


def _average_confidence(dimensions: dict[str, Any]) -> float:
    """Calculate average confidence across all dimensions."""
    if not dimensions:
        return 0.0
    confidences = [d.get("confidence", 0) for d in dimensions.values()]
    return sum(confidences) / len(confidences) if confidences else 0.0


class ProfileConversationService:
    """Service for managing profile extraction conversations.

    Flow:
        1. create_session() — starts a new conversation
        2. process_message() — handles each user turn (LLM extraction + next question)
        3. finalize() — creates StudentProfile + writes evidence
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    async def create_session(
        self,
        user_id: str,
        learning_goal: str,
        learning_goal_id: str | None = None,
        target_context: str | None = None,
    ) -> ProfileConversationSession:
        """Create a new profile conversation session.

        The *learning_goal* and *target_context* are persisted on the session
        row so downstream extraction logic can use them directly instead of
        reverse-engineering the goal from the first assistant message.
        """
        session = ProfileConversationSession(
            id=str(uuid.uuid4()),
            user_id=user_id,
            learning_goal_id=learning_goal_id,
            learning_goal_text=learning_goal,
            target_context=target_context,
            status=ProfileConversationStatus.ACTIVE.value,
            turn_count=0,
            extracted_dimensions={},
            completion_score=0.0,
        )
        self.db.add(session)

        # Add initial assistant message
        initial_question = build_initial_question(learning_goal)
        msg = ProfileConversationMessage(
            id=str(uuid.uuid4()),
            session_id=session.id,
            role=ProfileMessageRole.ASSISTANT.value,
            content=initial_question,
        )
        self.db.add(msg)
        await self.db.commit()
        await self.db.refresh(session)

        return session

    async def get_session(self, session_id: str, user_id: str) -> ProfileConversationSession | None:
        """Get a conversation session, ensuring ownership."""
        result = await self.db.execute(
            select(ProfileConversationSession).where(
                ProfileConversationSession.id == session_id,
                ProfileConversationSession.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_messages(self, session_id: str) -> list[ProfileConversationMessage]:
        """Get all messages for a conversation session, ordered by creation."""
        result = await self.db.execute(
            select(ProfileConversationMessage)
            .where(ProfileConversationMessage.session_id == session_id)
            .order_by(ProfileConversationMessage.created_at)
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Message processing
    # ------------------------------------------------------------------

    async def process_message(
        self,
        session: ProfileConversationSession,
        user_message: str,
    ) -> dict[str, Any]:
        """Process a user message and return the assistant response.

        Returns:
            Dict with:
              - assistant_message: str
              - extracted_dimensions: dict
              - missing_dimensions: list[str]
              - ready_to_finalize: bool
        """
        # Save user message
        user_msg = ProfileConversationMessage(
            id=str(uuid.uuid4()),
            session_id=session.id,
            role=ProfileMessageRole.USER.value,
            content=user_message,
        )
        self.db.add(user_msg)

        # Get conversation history
        messages = await self.get_messages(session.id)
        history = [{"role": msg.role, "content": msg.content} for msg in messages]

        # Determine covered dimensions
        covered = self._get_covered_dimensions(session.extracted_dimensions)

        # Use the persisted learning goal text (E0-A1)
        learning_goal = session.learning_goal_text or self._get_learning_goal_from_history(history)

        # Try LLM extraction
        try:
            result = await self._llm_extract(
                learning_goal=learning_goal,
                history=history,
                user_message=user_message,
                covered_dimensions=covered,
                turn_count=session.turn_count,
            )
        except (LLMError, Exception) as e:
            logger.warning("profile_llm_fallback", error=str(e))
            result = self._fallback_extract(user_message, covered, session.turn_count)

        # Update session state — copy-then-assign for JSON persistence (E0-A2)
        new_extracted = self._merge_extracted(dict(session.extracted_dimensions or {}), result["extracted_dimensions"])
        session.extracted_dimensions = new_extracted
        session.turn_count += 1

        # Store extraction signals on the user message
        user_msg.extracted_signals = result["extracted_dimensions"]

        # Determine if ready to finalize
        covered_after = self._get_covered_dimensions(new_extracted)
        avg_confidence = self._average_confidence(new_extracted)
        ready = self._should_finalize(
            turn_count=session.turn_count,
            covered_count=len(covered_after),
            avg_confidence=avg_confidence,
        )
        result["ready_to_finalize"] = ready or session.turn_count >= MAX_TURNS

        # Update completion score
        session.completion_score = len(covered_after) / len(PROFILE_DIMENSIONS)

        # Generate next question
        if not result["ready_to_finalize"]:
            next_q = result.get("next_question") or self._fallback_next_question(covered_after, session.turn_count)
        else:
            next_q = "感谢你的回答！我已经收集了足够的信息来生成你的学习画像。点击「完成画像」按钮查看结果。"

        # Save assistant message
        assistant_msg = ProfileConversationMessage(
            id=str(uuid.uuid4()),
            session_id=session.id,
            role=ProfileMessageRole.ASSISTANT.value,
            content=next_q,
        )
        self.db.add(assistant_msg)

        await self.db.commit()
        await self.db.refresh(session)

        return {
            "assistant_message": next_q,
            "extracted_dimensions": new_extracted,
            "missing_dimensions": result.get("missing_dimensions", []),
            "ready_to_finalize": result["ready_to_finalize"],
        }

    # ------------------------------------------------------------------
    # Finalize
    # ------------------------------------------------------------------

    @staticmethod
    def can_finalize(session: ProfileConversationSession) -> bool:
        """Check whether a session meets the minimum requirements for finalize.

        Enforced server-side so the frontend cannot bypass it (E0-A5).

        Fallback path: when ``turn_count`` reaches ``MAX_TURNS`` the session
        is always finalizable.  This guarantees that conversations running
        under rule-based fallback (LLM unavailable) — which can only extract
        a limited number of low-confidence dimensions — are not permanently
        blocked from completing.
        """
        extracted = session.extracted_dimensions or {}

        # Fallback: max turns reached → allow finalize regardless of
        # dimension coverage or confidence (E0-A5 fallback).
        if session.turn_count >= MAX_TURNS:
            return True

        if session.turn_count < MIN_TURNS:
            return False
        if len(extracted) < MIN_DIMENSIONS_COVERED:
            return False
        avg_confidence = _average_confidence(extracted)
        return avg_confidence >= MIN_AVG_CONFIDENCE

    async def finalize(self, session: ProfileConversationSession) -> StudentProfile:
        """Finalize the conversation and create/update the student profile.

        Delegates all dimension merging and evidence writing to
        ``profile_merge.apply_profile_evidence()`` to ensure a single,
        idempotent code path (E0-A3).
        """
        from app.services.profile_merge import ProfileEvidenceInput, apply_profile_evidence

        extracted = session.extracted_dimensions or {}

        # Build evidence inputs from extracted dimensions
        evidence_inputs: list[ProfileEvidenceInput] = []
        for dim_name, dim_data in extracted.items():
            if dim_name not in PROFILE_DIMENSIONS:
                continue

            value = dim_data.get("value", 0)
            confidence = dim_data.get("confidence", 0.5)

            evidence_inputs.append(
                ProfileEvidenceInput(
                    dimension=dim_name,
                    value=value,
                    confidence=confidence,
                    evidence_type=ProfileEvidenceType.CONVERSATION_PROFILE.value,
                    evidence_id=session.id,
                    evidence_text=dim_data.get("evidence_text", ""),
                    metadata={
                        "session_id": session.id,
                        "learning_goal": session.learning_goal_text,
                        "target_context": session.target_context,
                        "rationale": dim_data.get("rationale_summary", ""),
                        "raw_value": value,
                    },
                )
            )

        # Single entry point for all profile updates (E0-A3)
        profile = await apply_profile_evidence(
            self.db,
            user_id=session.user_id,
            evidence=evidence_inputs,
        )

        # Generate summary from extracted dimensions
        profile.summary = self._generate_summary(extracted)

        # Link session to profile
        session.profile_id = profile.id
        session.status = ProfileConversationStatus.COMPLETED.value
        from app.common.datetime import utc_now

        session.completed_at = utc_now()

        await self.db.commit()
        await self.db.refresh(profile)

        logger.info(
            "profile_finalized",
            user_id=session.user_id,
            profile_id=profile.id,
            version=profile.profile_version,
            confidence=profile.confidence,
            dimensions=len(profile.dimensions),
        )

        return profile

    # ------------------------------------------------------------------
    # Public read methods
    # ------------------------------------------------------------------

    async def get_profile(self, user_id: str) -> StudentProfile | None:
        """Get the student profile for a user."""
        result = await self.db.execute(select(StudentProfile).where(StudentProfile.user_id == user_id))
        return result.scalar_one_or_none()

    async def get_evidence(self, user_id: str) -> list[StudentProfileEvidence]:
        """Get all evidence records for a user."""
        result = await self.db.execute(
            select(StudentProfileEvidence)
            .where(StudentProfileEvidence.user_id == user_id)
            .order_by(StudentProfileEvidence.created_at.desc())
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _llm_extract(
        self,
        learning_goal: str,
        history: list[dict[str, str]],
        user_message: str,
        covered_dimensions: list[str],
        turn_count: int,
    ) -> dict[str, Any]:
        """Call LLM to extract profile dimensions from user message."""
        user_prompt = build_profile_conversation_user_message(
            learning_goal=learning_goal,
            conversation_history=history,
            user_message=user_message,
            covered_dimensions=covered_dimensions,
            turn_count=turn_count,
        )

        raw = await llm_json(
            PROFILE_CONVERSATION_SYSTEM,
            user_prompt,
            temperature=0.3,
            max_tokens=2048,
        )

        # Validate and normalize
        extracted = []
        for dim in raw.get("extracted_dimensions", []):
            dim_name = dim.get("dimension", "")
            if dim_name in PROFILE_DIMENSIONS:
                extracted.append(
                    {
                        "dimension": dim_name,
                        "value": dim.get("value"),
                        "confidence": max(0.0, min(1.0, float(dim.get("confidence", 0.5)))),
                        "evidence_text": dim.get("evidence_text", ""),
                        "rationale_summary": dim.get("rationale_summary", ""),
                    }
                )

        missing = [
            d
            for d in PROFILE_DIMENSIONS
            if d not in covered_dimensions and d not in [e["dimension"] for e in extracted]
        ]

        return {
            "extracted_dimensions": extracted,
            "missing_dimensions": missing,
            "next_question": raw.get("next_question"),
            "ready_to_finalize": raw.get("ready_to_finalize", False),
        }

    def _fallback_extract(
        self,
        user_message: str,
        covered_dimensions: list[str],
        turn_count: int,
    ) -> dict[str, Any]:
        """Rule-based fallback extraction when LLM is unavailable."""
        extracted = []
        msg_lower = user_message.lower()

        # Simple keyword-based extraction
        if "knowledge_depth" not in covered_dimensions and any(
            w in msg_lower for w in ["基础", "入门", "会一点", "学过", "没学过", "不会"]
        ):
            level = 0.2 if any(w in msg_lower for w in ["没学过", "不会", "零基础"]) else 0.4
            extracted.append(
                {
                    "dimension": "knowledge_depth",
                    "value": level,
                    "confidence": 0.5,
                    "evidence_text": user_message[:100],
                    "rationale_summary": "Fallback: keyword-based knowledge depth estimation",
                }
            )

        if "learning_pace" not in covered_dimensions and any(
            w in msg_lower for w in ["每天", "小时", "时间", "快", "慢"]
        ):
            pace = "moderate"
            if any(w in msg_lower for w in ["快", "密集"]):
                pace = "fast"
            elif any(w in msg_lower for w in ["慢", "少"]):
                pace = "slow"
            extracted.append(
                {
                    "dimension": "learning_pace",
                    "value": pace,
                    "confidence": 0.4,
                    "evidence_text": user_message[:100],
                    "rationale_summary": "Fallback: keyword-based pace estimation",
                }
            )

        if "resource_preference" not in covered_dimensions:
            prefs: list[str] = []
            if any(w in msg_lower for w in ["视频", "看"]):
                prefs.append("video")
            if any(w in msg_lower for w in ["文档", "读", "书"]):
                prefs.append("reading")
            if any(w in msg_lower for w in ["项目", "实战", "做"]):
                prefs.append("project")
            if any(w in msg_lower for w in ["题", "练习"]):
                prefs.append("quiz")
            if prefs:
                extracted.append(
                    {
                        "dimension": "resource_preference",
                        "value": prefs,
                        "confidence": 0.4,
                        "evidence_text": user_message[:100],
                        "rationale_summary": "Fallback: keyword-based preference estimation",
                    }
                )

        missing = [
            d
            for d in PROFILE_DIMENSIONS
            if d not in covered_dimensions and d not in [e["dimension"] for e in extracted]
        ]
        next_q = self._fallback_next_question(covered_dimensions + [str(e["dimension"]) for e in extracted], turn_count)

        return {
            "extracted_dimensions": extracted,
            "missing_dimensions": missing,
            "next_question": next_q,
            "ready_to_finalize": False,
        }

    def _fallback_next_question(self, covered: list[str], turn_count: int) -> str:
        """Get the next fallback question based on turn count."""
        idx = min(turn_count, len(FALLBACK_QUESTIONS) - 1)
        return FALLBACK_QUESTIONS[idx]

    def _merge_extracted(
        self,
        current: dict[str, Any],
        new_extracted: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Merge newly extracted dimensions into the current state."""
        merged = dict(current)
        for item in new_extracted:
            dim = item["dimension"]
            if dim in merged:
                # Keep the one with higher confidence
                old_conf = merged[dim].get("confidence", 0)
                new_conf = item.get("confidence", 0)
                if new_conf >= old_conf:
                    merged[dim] = item
            else:
                merged[dim] = item
        return merged

    def _get_covered_dimensions(self, extracted: dict[str, Any]) -> list[str]:
        """Get list of dimensions that have been extracted with confidence > 0."""
        return [dim for dim, data in extracted.items() if data.get("confidence", 0) > 0]

    def _average_confidence(self, dimensions: dict[str, Any]) -> float:
        """Calculate average confidence across all dimensions."""
        return _average_confidence(dimensions)

    def _should_finalize(self, turn_count: int, covered_count: int, avg_confidence: float) -> bool:
        """Determine if the conversation is ready to finalize."""
        if turn_count < MIN_TURNS:
            return False
        if turn_count >= MAX_TURNS:
            return True
        return covered_count >= MIN_DIMENSIONS_COVERED and avg_confidence >= MIN_AVG_CONFIDENCE

    def _get_learning_goal_from_history(self, history: list[dict[str, str]]) -> str:
        """Extract the learning goal from the first assistant message."""
        if not history:
            return "未指定的学习目标"
        first = history[0]
        return first.get("content", "未指定的学习目标")

    def _generate_summary(self, dimensions: dict[str, Any]) -> str:
        """Generate a human-readable profile summary."""
        parts: list[str] = []
        for dim_name, data in dimensions.items():
            value = data.get("value")
            if isinstance(value, float):
                parts.append(f"{dim_name}={value:.2f}")
            else:
                parts.append(f"{dim_name}={value}")
        return "；".join(parts) if parts else "画像数据较少，后续会根据学习过程自动修正。"

    async def _get_or_create_profile(self, user_id: str) -> StudentProfile:
        """Get existing profile or create a new one.

        Deprecated: prefer ``profile_merge.apply_profile_evidence()`` which
        handles profile creation internally.  Kept for backwards compatibility.
        """
        from app.common.enums import ProfileStatus

        result = await self.db.execute(select(StudentProfile).where(StudentProfile.user_id == user_id))
        profile = result.scalar_one_or_none()
        if profile is None:
            profile = StudentProfile(
                id=str(uuid.uuid4()),
                user_id=user_id,
                status=ProfileStatus.ACTIVE.value,
                profile_version=0,
                dimensions={},
                confidence=0.0,
            )
            self.db.add(profile)
            await self.db.flush()
        return profile
