"""Clarification models for persistent question/answer storage."""

from __future__ import annotations

import uuid
from datetime import datetime  # noqa: TC003

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class ClarificationSet(Base):
    """A set of clarification questions for a goal."""

    __tablename__ = "goal_clarification_sets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    goal_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_goals.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ClarificationQuestion(Base):
    """A single clarification question."""

    __tablename__ = "goal_clarification_questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    set_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("goal_clarification_sets.id"), nullable=False, index=True
    )
    question_type: Mapped[str] = mapped_column(String(20), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    options: Mapped[list | None] = mapped_column(JSON, nullable=True)
    min_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    question_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ClarificationAnswer(Base):
    """An answer to a clarification question."""

    __tablename__ = "goal_clarification_answers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    question_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("goal_clarification_questions.id"), nullable=False, index=True
    )
    goal_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_goals.id"), nullable=False, index=True)
    answer_value: Mapped[str] = mapped_column(Text, nullable=False)  # JSON encoded
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
