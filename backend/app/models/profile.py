"""Conversational 8-dimensional learner profile models.

Implements the Phase 3.6 profile domain:
  - StudentProfile: versioned 8-dimensional learner profile
  - ProfileConversationSession: multi-turn conversation for profile extraction
  - ProfileConversationMessage: individual messages in a conversation session

The eight core dimensions are:
  1. knowledge_depth       — current knowledge base depth
  2. prerequisite_mastery   — prerequisite knowledge mastery
  3. concept_grasp         — concept understanding ability
  4. problem_solving       — problem-solving ability
  5. practice_ability      — hands-on practice and transfer ability
  6. learning_pace         — learning rhythm and digestion speed
  7. resource_preference   — resource preferences (visual, video, code, etc.)
  8. error_pattern         — common error patterns and weak points
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from datetime import datetime


def generate_uuid() -> str:
    return str(uuid.uuid4())


class StudentProfile(Base):
    """Versioned 8-dimensional learner profile.

    Each user has at most one active profile. The ``dimensions`` JSON
    stores the eight core dimensions with their current value, confidence,
    and source. ``profile_version`` increments on every merge operation.
    """

    __tablename__ = "student_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    dimensions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    conversation_sessions: Mapped[list[ProfileConversationSession]] = relationship(
        "ProfileConversationSession", back_populates="profile", foreign_keys="ProfileConversationSession.profile_id"
    )


class ProfileConversationSession(Base):
    """Multi-turn conversation session for profile extraction.

    Status lifecycle: active → completed | cancelled | expired

    The conversation runs 3–7 turns, extracting dimensional signals
    from user responses. ``extracted_dimensions`` accumulates the
    extracted data during the conversation. ``completion_score``
    tracks how many of the 8 dimensions have been covered.
    """

    __tablename__ = "profile_conversation_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    learning_goal_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("learning_goals.id"), nullable=True, index=True
    )
    profile_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("student_profiles.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    turn_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extracted_dimensions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    completion_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    profile: Mapped[StudentProfile | None] = relationship(
        "StudentProfile", back_populates="conversation_sessions", foreign_keys=[profile_id]
    )
    messages: Mapped[list[ProfileConversationMessage]] = relationship(
        "ProfileConversationMessage", back_populates="session", cascade="all, delete-orphan"
    )


class ProfileConversationMessage(Base):
    """Individual message in a profile conversation.

    Roles:
      - ``user``: the learner's natural-language response
      - ``assistant``: the system's question or prompt
      - ``system_summary``: a structured summary message (not shown to user)

    ``extracted_signals`` stores the structured extraction result for
    ``user`` messages. Only user-visible content and structured extraction
    results are stored — no internal prompts, model configs, or chain-of-thought.
    """

    __tablename__ = "profile_conversation_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("profile_conversation_sessions.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    extracted_signals: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    session: Mapped[ProfileConversationSession] = relationship("ProfileConversationSession", back_populates="messages")
