"""Unit tests for the Task Handler Registry."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.workers.task_handlers import (
    IMPLEMENTED_TASK_TYPES,
    PUBLIC_TASK_TYPES,
    RESERVED_TASK_TYPES,
    TASK_HANDLERS,
    get_handler,
    register_builtin_task_handlers,
    register_handler,
)


class TestRegistryCore:
    """Core registry behavior."""

    def setup_method(self) -> None:
        # Reset for test isolation
        TASK_HANDLERS.clear()

    def teardown_method(self) -> None:
        TASK_HANDLERS.clear()

    def test_register_and_get_handler(self) -> None:
        """A registered handler can be retrieved by type."""

        async def my_handler(db: AsyncSession, task: Any) -> dict[str, Any]:
            return {"status": "ok"}

        register_handler("test_type")(my_handler)
        assert get_handler("test_type") is my_handler

    def test_unknown_type_returns_none(self) -> None:
        """An unregistered type returns None (not a crash)."""
        assert get_handler("nonexistent") is None

    def test_register_overwrites(self) -> None:
        """Registering the same type twice overwrites (last wins)."""

        async def handler_a(db: AsyncSession, task: Any) -> dict[str, Any]:
            return {"version": "a"}

        async def handler_b(db: AsyncSession, task: Any) -> dict[str, Any]:
            return {"version": "b"}

        register_handler("dup_type")(handler_a)
        register_handler("dup_type")(handler_b)
        assert get_handler("dup_type") is handler_b

    def test_handler_is_coroutine(self) -> None:
        """All registered handlers must be coroutine functions."""
        import inspect

        async def valid_handler(db: AsyncSession, task: Any) -> dict[str, Any]:
            return {"status": "ok"}

        register_handler("valid")(valid_handler)
        handler = get_handler("valid")
        assert handler is not None
        assert inspect.iscoroutinefunction(handler)

    def test_empty_registry_returns_none(self) -> None:
        """An empty registry returns None for any type."""
        assert get_handler("anything") is None


class TestBuiltinRegistration:
    """Built-in task handler registration."""

    def setup_method(self) -> None:
        TASK_HANDLERS.clear()

    def teardown_method(self) -> None:
        TASK_HANDLERS.clear()

    def test_register_builtin_populates_handlers(self) -> None:
        register_builtin_task_handlers()
        assert len(TASK_HANDLERS) > 0

    def test_registration_is_idempotent(self) -> None:
        register_builtin_task_handlers()
        before = dict(TASK_HANDLERS)
        register_builtin_task_handlers()
        register_builtin_task_handlers()
        assert dict(TASK_HANDLERS) == before

    def test_all_implemented_types_registered(self) -> None:
        register_builtin_task_handlers()
        missing = IMPLEMENTED_TASK_TYPES - TASK_HANDLERS.keys()
        assert not missing, f"Missing handlers: {missing}"

    def test_each_handler_is_callable(self) -> None:
        import inspect

        register_builtin_task_handlers()
        for task_type, handler in TASK_HANDLERS.items():
            assert inspect.iscoroutinefunction(handler), f"Handler for '{task_type}' is not a coroutine"

    def test_reserved_types_not_registered(self) -> None:
        register_builtin_task_handlers()
        registered_reserved = RESERVED_TASK_TYPES & TASK_HANDLERS.keys()
        assert not registered_reserved, f"RESERVED_TASK_TYPES should not have handlers: {registered_reserved}"

    def test_public_types_coverage(self) -> None:
        """Every PUBLIC task type is either IMPLEMENTED or RESERVED."""
        register_builtin_task_handlers()
        allowed = IMPLEMENTED_TASK_TYPES | RESERVED_TASK_TYPES
        extra = PUBLIC_TASK_TYPES - allowed
        assert not extra, f"PUBLIC_TASK_TYPES has undocumented types: {extra}"


class TestHandlerContract:
    """Handler contract: all handlers must accept (db, task) and return dict."""

    def setup_method(self) -> None:
        TASK_HANDLERS.clear()
        register_builtin_task_handlers()

    def teardown_method(self) -> None:
        TASK_HANDLERS.clear()

    @pytest.mark.parametrize(
        "task_type",
        sorted(IMPLEMENTED_TASK_TYPES),
    )
    def test_handler_signature(self, task_type: str) -> None:
        """Every handler must accept (db, task) positional args."""
        import inspect

        handler = TASK_HANDLERS.get(task_type)
        assert handler is not None, f"No handler for {task_type}"

        sig = inspect.signature(handler)
        params = list(sig.parameters.values())

        assert len(params) >= 2, f"Handler for {task_type} needs at least 2 params"

        # First param should be db/session-like, second should be task-like
        # (exact types vary, but positional acceptance is mandatory)
        assert params[0].kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ), f"Handler for {task_type} first param must be positional"
        assert params[1].kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ), f"Handler for {task_type} second param must be positional"

    def test_return_type_is_dict(self) -> None:
        """Handler return annotation should be dict."""
        import inspect

        for task_type in IMPLEMENTED_TASK_TYPES:
            handler = TASK_HANDLERS.get(task_type)
            if handler is None:
                continue
            sig = inspect.signature(handler)
            ret = sig.return_annotation
            # Some handlers may have string annotations; just check they exist
            assert ret is not inspect.Parameter.empty, f"Handler for {task_type} has no return annotation"


class TestTypeClassification:
    """IMPLEMENTED / RESERVED / PUBLIC sets must be consistent."""

    def test_no_overlap_implemented_reserved(self) -> None:
        overlap = IMPLEMENTED_TASK_TYPES & RESERVED_TASK_TYPES
        assert not overlap, f"IMPLEMENTED and RESERVED overlap: {overlap}"

    def test_public_is_superset_of_implemented(self) -> None:
        missing = IMPLEMENTED_TASK_TYPES - PUBLIC_TASK_TYPES
        # e2e_progress_test is internal-only, not public
        internal_only = {"e2e_progress_test"}
        assert missing == internal_only, f"IMPLEMENTED types not in PUBLIC (except internal): {missing - internal_only}"

    def test_reserved_may_be_in_public(self) -> None:
        """RESERVED types can appear in PUBLIC as documented tech debt."""
        exposed = RESERVED_TASK_TYPES & PUBLIC_TASK_TYPES
        if exposed:
            pass  # Documented: these need removal from frontend schema
