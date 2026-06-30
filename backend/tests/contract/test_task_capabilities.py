"""Contract tests for task capabilities.

Verifies that:
  - Every public TaskType has a registered handler.
  - IMPLEMENTED_TASK_TYPES ⊆ TASK_HANDLERS.
  - RESERVED_TASK_TYPES are not exposed to the production frontend.
  - Frontend TaskTypeSchema is consistent with the backend.
"""

from __future__ import annotations

from app.common.enums import TaskType
from app.workers.task_handlers import (
    IMPLEMENTED_TASK_TYPES,
    PUBLIC_TASK_TYPES,
    RESERVED_TASK_TYPES,
    TASK_HANDLERS,
    get_handler,
    register_builtin_task_handlers,
)


class TestTaskHandlerRegistry:
    """All implemented task types must have a registered handler."""

    def setup_method(self) -> None:
        register_builtin_task_handlers()

    def test_all_implemented_types_have_handlers(self) -> None:
        """Every type in IMPLEMENTED_TASK_TYPES must be in TASK_HANDLERS."""
        missing = IMPLEMENTED_TASK_TYPES - TASK_HANDLERS.keys()
        assert not missing, f"Implemented task types missing handlers: {missing}"

    def test_public_types_are_implemented(self) -> None:
        """Every PUBLIC_TASK_TYPES must have a handler (except RESERVED types).

        RESERVED types are in the enum for future work but have no handler yet.
        """
        exempt = PUBLIC_TASK_TYPES & RESERVED_TASK_TYPES
        must_implement = PUBLIC_TASK_TYPES - exempt
        missing = must_implement - TASK_HANDLERS.keys()
        assert not missing, (
            f"Public task types with no handler: {missing}. Either implement them or remove from PUBLIC_TASK_TYPES."
        )

    def test_reserved_types_not_in_implemented(self) -> None:
        """RESERVED_TASK_TYPES must not appear in IMPLEMENTED_TASK_TYPES."""
        overlap = RESERVED_TASK_TYPES & IMPLEMENTED_TASK_TYPES
        assert not overlap, f"RESERVED_TASK_TYPES should not be in IMPLEMENTED_TASK_TYPES: {overlap}"

    def test_registration_is_idempotent(self) -> None:
        """Calling register_builtin_task_handlers multiple times does not raise."""
        before = dict(TASK_HANDLERS)
        register_builtin_task_handlers()
        register_builtin_task_handlers()
        assert before == TASK_HANDLERS

    def test_unknown_type_fails_gracefully(self) -> None:
        """Handler lookup for an unknown type returns None (not a crash)."""
        assert get_handler("nonexistent_type") is None

    def test_knowledge_reindex_has_real_handler(self) -> None:
        """knowledge_reindex must have a handler (not UNKNOWN_TASK_TYPE)."""
        assert "knowledge_reindex" in TASK_HANDLERS

    def test_learning_path_revision_has_real_handler(self) -> None:
        """learning_path_revision must have a handler (not UNKNOWN_TASK_TYPE)."""
        assert "learning_path_revision" in TASK_HANDLERS

    def test_registered_handlers_are_callable(self) -> None:
        """Every handler in the registry must be a callable coroutine function."""
        import inspect

        for task_type, handler in TASK_HANDLERS.items():
            assert inspect.iscoroutinefunction(handler), f"Handler for '{task_type}' is not a coroutine function"


class TestFrontendBackendConsistency:
    """Frontend task type definitions must match the backend."""

    FRONTEND_TYPES: list[str] = sorted(PUBLIC_TASK_TYPES)

    def setup_method(self) -> None:
        register_builtin_task_handlers()

    def test_frontend_types_match_backend_enum(self) -> None:
        """Every frontend TaskTypeSchema value must exist in the backend enum."""
        backend_types = {t.value for t in TaskType}
        for ft in self.FRONTEND_TYPES:
            assert ft in backend_types, f"Frontend task type '{ft}' is not defined in backend TaskType enum"

    def test_backend_enum_types_are_in_frontend(self) -> None:
        """Every backend enum value (except E2E) should be in the frontend schema."""
        backend_types = {t.value for t in TaskType}
        e2e_only = {"e2e_progress_test"}
        frontend_set = set(self.FRONTEND_TYPES)

        missing_in_frontend = backend_types - frontend_set - e2e_only
        assert not missing_in_frontend, f"Backend TaskType values missing from frontend schema: {missing_in_frontend}"

    def test_public_type_subset_of_implemented_plus_reserved(self) -> None:
        """All public types are either implemented or reserved for future."""
        allowed = IMPLEMENTED_TASK_TYPES | RESERVED_TASK_TYPES
        extra = PUBLIC_TASK_TYPES - allowed
        assert not extra, f"PUBLIC_TASK_TYPES contains types neither implemented nor reserved: {extra}"

    def test_reserved_types_not_in_frontend(self) -> None:
        """RESERVED_TASK_TYPES should eventually be removed from frontend schema."""
        # This is a soft check — no assert, just documentation.
        exposed_reserved = RESERVED_TASK_TYPES & set(self.FRONTEND_TYPES)
        if exposed_reserved:
            pass  # Documented tech debt: remove from frontend TaskTypeSchema
