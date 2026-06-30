"""Diagnostic assessment models for real scoring."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

if TYPE_CHECKING:
    from datetime import datetime


def generate_uuid() -> str:
    return str(uuid.uuid4())


class DiagnosticQuestion(Base):
    """A question within a diagnostic assessment."""

    __tablename__ = "diagnostic_questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    diagnostic_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    question_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # single_choice, multiple_choice, true_false, short_answer
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    correct_answer: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    rubric: Mapped[str | None] = mapped_column(Text, nullable=True)
    dimension: Mapped[str | None] = mapped_column(String(100), nullable=True)
    difficulty: Mapped[str | None] = mapped_column(String(30), nullable=True)
    max_score: Mapped[float] = mapped_column(Float, nullable=False, default=10.0)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    required: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DiagnosticAttempt(Base):
    """A user's attempt at a diagnostic assessment."""

    __tablename__ = "diagnostic_attempts"
    __table_args__ = (Index("ix_diagnostic_attempts_user_goal", "user_id", "goal_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    diagnostic_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    goal_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_goals.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", index=True
    )  # draft, submitted, grading, completed, failed
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    grading_quality: Mapped[str | None] = mapped_column(String(20), nullable=True)  # final, provisional
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class DiagnosticAnswer(Base):
    """A user's answer to a specific diagnostic question."""

    __tablename__ = "diagnostic_answers"
    __table_args__ = (UniqueConstraint("attempt_id", "question_id", name="uq_diagnostic_answer_attempt_question"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    attempt_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("diagnostic_attempts.id"), nullable=False, index=True
    )
    question_id: Mapped[str] = mapped_column(String(36), nullable=False)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    max_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_correct: Mapped[bool | None] = mapped_column(nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    grading_source: Mapped[str | None] = mapped_column(String(20), nullable=True)  # program, llm, fallback
    grading_status: Mapped[str | None] = mapped_column(String(20), nullable=True)  # graded, provisional, failed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class DiagnosticResult(Base):
    """Aggregated result for a diagnostic attempt."""

    __tablename__ = "diagnostic_results"
    __table_args__ = (UniqueConstraint("attempt_id", name="uq_diagnostic_result_attempt"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    attempt_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("diagnostic_attempts.id"), nullable=False, unique=True, index=True
    )
    total_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    percentage: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    dimension_scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    strong_areas: Mapped[list | None] = mapped_column(JSON, nullable=True)
    weak_areas: Mapped[list | None] = mapped_column(JSON, nullable=True)
    readiness_level: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # beginner, intermediate, proficient, advanced
    grading_quality: Mapped[str | None] = mapped_column(String(20), nullable=True)  # final, provisional
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
