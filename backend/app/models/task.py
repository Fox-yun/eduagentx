"""Background task and task event models."""

from __future__ import annotations

import uuid
from datetime import datetime  # noqa: TC003

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.common.enums import TaskStatus
from app.core.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class BackgroundTask(Base):
    """Background task for async operations."""

    __tablename__ = "background_tasks"
    __table_args__ = (Index("ix_background_tasks_user_status", "user_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default=TaskStatus.PENDING.value, index=True)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_stage: Mapped[str | None] = mapped_column(String(100), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    target_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    agent_trace: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_event_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    worker_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class TaskEvent(Base):
    """Task event for SSE streaming."""

    __tablename__ = "task_events"
    __table_args__ = (UniqueConstraint("task_id", "sequence_number", name="uq_task_event_sequence"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("background_tasks.id"), nullable=False, index=True)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stage: Mapped[str | None] = mapped_column(String(100), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# Valid task state transitions
TASK_STATE_TRANSITIONS: dict[str, set[str]] = {
    TaskStatus.PENDING.value: {TaskStatus.RUNNING.value, TaskStatus.CANCELLED.value, TaskStatus.EXPIRED.value},
    TaskStatus.RUNNING.value: {
        TaskStatus.COMPLETED.value,
        TaskStatus.PARTIAL_COMPLETED.value,
        TaskStatus.FAILED.value,
        TaskStatus.CANCEL_REQUESTED.value,
        TaskStatus.INTERRUPTED.value,
    },
    TaskStatus.CANCEL_REQUESTED.value: {
        TaskStatus.CANCELLED.value,
        TaskStatus.COMPLETED.value,
        TaskStatus.FAILED.value,
    },
    TaskStatus.COMPLETED.value: set(),
    TaskStatus.PARTIAL_COMPLETED.value: set(),
    TaskStatus.FAILED.value: {TaskStatus.PENDING.value},  # Can retry
    TaskStatus.CANCELLED.value: set(),
    TaskStatus.EXPIRED.value: set(),
    TaskStatus.INTERRUPTED.value: {TaskStatus.PENDING.value, TaskStatus.FAILED.value},
}


def validate_task_transition(current: str, target: str) -> bool:
    """Validate that a task state transition is allowed."""
    allowed = TASK_STATE_TRANSITIONS.get(current, set())
    return target in allowed
