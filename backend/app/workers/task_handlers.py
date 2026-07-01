"""Centralized Task Handler Registry.

Maps task_type strings to their async handler functions.
Both the Celery worker and inline runner MUST use this registry
to dispatch tasks — no if/elif chains.

Usage:
    from app.workers.task_handlers import (
        register_builtin_task_handlers,
        get_handler,
    )

    # Call once at startup
    register_builtin_task_handlers()

    handler = get_handler(task.task_type)
    if handler is None:
        # Unknown task type — mark task as failed
        ...
    result = await handler(db, task)
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import BackgroundTask

TaskHandler = Callable[[AsyncSession, BackgroundTask], Awaitable[dict[str, Any]]]

TASK_HANDLERS: dict[str, TaskHandler] = {}

#: Task types with a production-ready handler implementation.
IMPLEMENTED_TASK_TYPES: frozenset[str] = frozenset(
    {
        "diagnostic_grading",
        "learning_path_generation",
        "learning_path_revision",
        "learning_unit_generation",
        "learning_lecture_generation",
        "learning_assessment_generation",
        "assessment_grading",
        "knowledge_index",
        "knowledge_reindex",
        "e2e_progress_test",
    }
)

#: Task types reserved for future phases — NOT exposed to production frontend.
RESERVED_TASK_TYPES: frozenset[str] = frozenset(
    {
        "learning_goal_analysis",
        "learning_diagnostic_generation",
        "learning_path_adaptation",
    }
)

#: Task types that appear in the frontend public TaskTypeSchema.
PUBLIC_TASK_TYPES: frozenset[str] = frozenset(
    {
        "learning_goal_analysis",
        "learning_diagnostic_generation",
        "learning_path_generation",
        "learning_path_revision",
        "learning_unit_generation",
        "learning_assessment_generation",
        "assessment_grading",
        "learning_path_adaptation",
        "knowledge_index",
        "knowledge_reindex",
        "learning_lecture_generation",
    }
)


def register_handler(task_type: str) -> Callable[[TaskHandler], TaskHandler]:
    """Decorator to register a task handler for the given task_type."""

    def decorator(func: TaskHandler) -> TaskHandler:
        TASK_HANDLERS[task_type] = func
        return func

    return decorator


def get_handler(task_type: str) -> TaskHandler | None:
    """Return the registered handler for *task_type*, or None."""
    return TASK_HANDLERS.get(task_type)


def register_builtin_task_handlers() -> None:
    """Explicitly register all built-in task handlers.

    Idempotent — safe to call multiple times.
    Must be called at every entry point (Celery worker, inline runner,
    contract tests, app startup) before dispatching tasks.
    """
    # Lazy imports to avoid circular dependencies at module level
    from app.workers.diagnostic_grading import execute_diagnostic_grading

    _register_if_missing("diagnostic_grading", execute_diagnostic_grading)

    from app.workers.path_revision import execute_path_revision

    _register_if_missing("learning_path_revision", execute_path_revision)

    from app.workers.tasks import (
        _execute_e2e_progress_task,
        _execute_knowledge_index,
        _execute_knowledge_reindex,
        _execute_lecture_generation,
        _execute_path_generation,
        _execute_unit_generation,
    )

    _register_if_missing("e2e_progress_test", _execute_e2e_progress_task)
    _register_if_missing("knowledge_index", _execute_knowledge_index)
    _register_if_missing("knowledge_reindex", _execute_knowledge_reindex)
    _register_if_missing("learning_lecture_generation", _execute_lecture_generation)
    _register_if_missing("learning_path_generation", _execute_path_generation)
    _register_if_missing("learning_unit_generation", _execute_unit_generation)

    from app.workers.assessment_generation import execute_assessment_generation

    _register_if_missing("learning_assessment_generation", execute_assessment_generation)

    from app.workers.assessment_grading import execute_assessment_grading

    _register_if_missing("assessment_grading", execute_assessment_grading)


def _register_if_missing(task_type: str, handler: TaskHandler) -> None:
    """Register a handler if not already present (idempotent)."""
    if task_type not in TASK_HANDLERS:
        TASK_HANDLERS[task_type] = handler
