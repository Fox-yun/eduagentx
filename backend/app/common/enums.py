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
    DIAGNOSTIC_GRADING = "diagnostic_grading"
    LEARNING_PATH_GENERATION = "learning_path_generation"
    LEARNING_PATH_REVISION = "learning_path_revision"
    LEARNING_UNIT_GENERATION = "learning_unit_generation"
    LEARNING_ASSESSMENT_GENERATION = "learning_assessment_generation"
    ASSESSMENT_GRADING = "assessment_grading"
    LEARNING_PATH_ADAPTATION = "learning_path_adaptation"
    KNOWLEDGE_INDEX = "knowledge_index"
    KNOWLEDGE_REINDEX = "knowledge_reindex"
    LEARNING_LECTURE_GENERATION = "learning_lecture_generation"
    INTERACTIVE_RESOURCE_GENERATION = "interactive_resource_generation"


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


class ProfileStatus(enum.StrEnum):
    """Student profile lifecycle states."""

    ACTIVE = "active"
    PROVISIONAL = "provisional"
    ARCHIVED = "archived"


class ProfileConversationStatus(enum.StrEnum):
    """Profile conversation session states."""

    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ProfileMessageRole(enum.StrEnum):
    """Profile conversation message roles."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM_SUMMARY = "system_summary"


class ProfileEvidenceType(enum.StrEnum):
    """Evidence types for student profile updates."""

    CONVERSATION_PROFILE = "conversation_profile"
    ASSESSMENT_ATTEMPT = "assessment_attempt"
    DIAGNOSTIC_RESULT = "diagnostic_result"
    LEARNING_BEHAVIOR = "learning_behavior"
    MANUAL_CORRECTION = "manual_correction"


# The eight core profile dimensions
PROFILE_DIMENSIONS: tuple[str, ...] = (
    "knowledge_depth",
    "prerequisite_mastery",
    "concept_grasp",
    "problem_solving",
    "practice_ability",
    "learning_pace",
    "resource_preference",
    "error_pattern",
)


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
