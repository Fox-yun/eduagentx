"""Unit content and assessment models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

if TYPE_CHECKING:
    from datetime import datetime


def generate_uuid() -> str:
    return str(uuid.uuid4())


class LearningUnitContent(Base):
    """Generated content for a learning node."""

    __tablename__ = "learning_unit_contents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    path_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_paths.id"), nullable=False, index=True)
    path_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    node_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="not_generated")
    content: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    citations: Mapped[list | None] = mapped_column(JSON, nullable=True)
    generation_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Assessment(Base):
    """Assessment for a learning node."""

    __tablename__ = "assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    path_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_paths.id"), nullable=False, index=True)
    path_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    node_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AssessmentQuestion(Base):
    """A question within an assessment."""

    __tablename__ = "assessment_questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    assessment_id: Mapped[str] = mapped_column(String(36), ForeignKey("assessments.id"), nullable=False, index=True)
    question_type: Mapped[str] = mapped_column(String(30), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list | None] = mapped_column(JSON, nullable=True)
    correct_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    points: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    question_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class AssessmentAttempt(Base):
    """An attempt at an assessment."""

    __tablename__ = "assessment_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    assessment_id: Mapped[str] = mapped_column(String(36), ForeignKey("assessments.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="in_progress")
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    weak_concepts: Mapped[list | None] = mapped_column(JSON, nullable=True)
    explanations: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    recommended_actions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AssessmentAnswer(Base):
    """An answer to a specific question in an attempt."""

    __tablename__ = "assessment_answers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    attempt_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("assessment_attempts.id"), nullable=False, index=True
    )
    question_id: Mapped[str] = mapped_column(String(36), ForeignKey("assessment_questions.id"), nullable=False)
    answer_value: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    points_earned: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
