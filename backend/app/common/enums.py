"""Common enumerations used across the application."""

from __future__ import annotations

import enum


class TaskStatus(enum.StrEnum):
    """Task lifecycle states."""

    PENDING = "pending"
    RUNNING = "running"
    CANCEL_REQUESTED = "cancel_requested"
    COMPLETED = "completed"
    PARTIAL_COMPLETED = "partial_completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    INTERRUPTED = "interrupted"


class TaskType(enum.StrEnum):
    """Task type identifiers."""

    LEARNING_GOAL_ANALYSIS = "learning_goal_analysis"
    LEARNING_DIAGNOSTIC_GENERATION = "learning_diagnostic_generation"
    LEARNING_PATH_GENERATION = "learning_path_generation"
    LEARNING_PATH_REVISION = "learning_path_revision"
    LEARNING_UNIT_GENERATION = "learning_unit_generation"
    LEARNING_ASSESSMENT_GENERATION = "learning_assessment_generation"
    LEARNING_PATH_ADAPTATION = "learning_path_adaptation"
    KNOWLEDGE_INDEX = "knowledge_index"
    KNOWLEDGE_REINDEX = "knowledge_reindex"


class TaskEventType(enum.StrEnum):
    """Task event types for SSE."""

    SNAPSHOT = "snapshot"
    PROGRESS = "progress"
    MESSAGE = "message"
    COMPLETED = "completed"
    PARTIAL_COMPLETED = "partial_completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    HEARTBEAT = "heartbeat"


class UserStatus(enum.StrEnum):
    """User account status."""

    PENDING_VERIFICATION = "pending_verification"
    ACTIVE = "active"
    LOCKED = "locked"
    DISABLED = "disabled"
    DELETED = "deleted"


TERMINAL_TASK_STATUSES: frozenset[TaskStatus] = frozenset(
    {
        TaskStatus.COMPLETED,
        TaskStatus.PARTIAL_COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
        TaskStatus.EXPIRED,
        TaskStatus.INTERRUPTED,
    }
)
