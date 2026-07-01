"""Unit content and assessment models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from datetime import datetime


def generate_uuid() -> str:
    return str(uuid.uuid4())


class LearningUnitContent(Base):
    """Generated content for a learning node — the root entity.

    Each node has exactly one LearningUnitContent row (enforced by UNIQUE(node_id)).
    Content versions are tracked in LearningUnitContentVersion.
    """

    __tablename__ = "learning_unit_contents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    path_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_paths.id"), nullable=False, index=True)
    path_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    node_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="not_generated")
    active_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("learning_unit_content_versions.id"), nullable=True
    )
    active_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Legacy columns — kept for backward compatibility during C1 migration.
    # Remove in a future migration after all reads use active_version.
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    citations: Mapped[list | None] = mapped_column(JSON, nullable=True)
    generation_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationship to versions through unit_content_id FK
    versions: Mapped[list[LearningUnitContentVersion]] = relationship(
        "LearningUnitContentVersion",
        back_populates="unit_content",
        foreign_keys="LearningUnitContentVersion.unit_content_id",
        lazy="selectin",
    )


class LearningUnitContentVersion(Base):
    """A versioned snapshot of generated unit content."""

    __tablename__ = "learning_unit_content_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    unit_content_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("learning_unit_contents.id"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="generating")
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="llm")
    quality_status: Mapped[str] = mapped_column(String(20), nullable=False, default="final")
    content: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    generation_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True, unique=True)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("unit_content_id", "version_number", name="uq_version_per_content"),)

    unit_content: Mapped[LearningUnitContent] = relationship(
        "LearningUnitContent",
        back_populates="versions",
        foreign_keys=[unit_content_id],
        lazy="selectin",
    )


class Assessment(Base):
    """Assessment for a learning node.

    Purpose distinguishes usage: quiz_bank (generated, browsable),
    formal (scored, one attempt), practice (repeatable, not scored).
    """

    __tablename__ = "assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    path_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_paths.id"), nullable=False, index=True)
    path_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    node_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False, default="quiz_bank")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    active_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AssessmentQuestion(Base):
    """A question within an assessment.

    Public DTO MUST exclude correct_answer, reference_answer, rubric,
    and explanation — these are only returned after submission/grading.
    """

    __tablename__ = "assessment_questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    assessment_id: Mapped[str] = mapped_column(String(36), ForeignKey("assessments.id"), nullable=False, index=True)
    question_type: Mapped[str] = mapped_column(String(30), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list | None] = mapped_column(JSON, nullable=True)
    correct_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    rubric: Mapped[list | None] = mapped_column(JSON, nullable=True)
    difficulty: Mapped[str | None] = mapped_column(String(10), nullable=True)
    knowledge_point: Mapped[str | None] = mapped_column(String(500), nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    points: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_score: Mapped[float | None] = mapped_column(Float, nullable=True)
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
    grading_quality: Mapped[str | None] = mapped_column(String(20), nullable=True)
    active_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    weak_concepts: Mapped[list | None] = mapped_column(JSON, nullable=True)
    explanations: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    recommended_actions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    progress_applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assessment_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    node_completed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    mastery_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    mastery_after: Mapped[float | None] = mapped_column(Float, nullable=True)
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
    max_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    grading_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    grading_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (UniqueConstraint("attempt_id", "question_id", name="uq_answer_per_question"),)


class LearningLecture(Base):
    """Independent lecture content for a learning node.

    Lecture is versioned independently from unit content so it can be
    regenerated without affecting the unit content version.
    """

    __tablename__ = "learning_lectures"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    path_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_paths.id"), nullable=False, index=True)
    node_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="not_generated")
    content: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    active_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
