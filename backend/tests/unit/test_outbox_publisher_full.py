"""Comprehensive unit tests for outbox_publisher module."""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _mock_scalars(items):
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


def _make_outbox_event(**overrides):
    e = MagicMock()
    e.id = overrides.get("id", "evt-1")
    e.event_type = overrides.get("event_type", "task.execute")
    e.aggregate_type = overrides.get("aggregate_type", "BackgroundTask")
    e.aggregate_id = overrides.get("aggregate_id", "task-1")
    e.payload = overrides.get("payload", {"task_id": "task-1", "task_type": "learning_path_generation"})
    e.status = overrides.get("status", "pending")
    e.attempt_count = overrides.get("attempt_count", 0)
    e.max_attempts = overrides.get("max_attempts", 5)
    e.available_at = overrides.get("available_at")
    e.last_error = overrides.get("last_error")
    e.published_at = None
    return e


def _create_mock_session(db):
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=db)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=mock_session)


@pytest.fixture(autouse=True)
def _mock_celery_imports():
    """Ensure celery-related imports don't fail."""
    saved = {}
    modules_to_mock = ["celery"]
    for mod_name in modules_to_mock:
        if mod_name in sys.modules:
            saved[mod_name] = sys.modules[mod_name]
        else:
            sys.modules[mod_name] = MagicMock()

    # Also ensure app.workers.tasks is importable by faking celery_app
    if "app.workers.celery_app" not in sys.modules:
        fake_celery_app = ModuleType("app.workers.celery_app")
        fake_celery_app.celery_app = MagicMock()  # type: ignore[attr-defined]
        sys.modules["app.workers.celery_app"] = fake_celery_app

    yield

    for mod_name in modules_to_mock:
        if mod_name in saved:
            sys.modules[mod_name] = saved[mod_name]
        elif mod_name in sys.modules:
            del sys.modules[mod_name]


class TestPublishPendingOutbox:
    @pytest.mark.asyncio
    async def test_publish_events_success(self):
        from app.workers.outbox_publisher import publish_pending_outbox

        event = _make_outbox_event()
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_factory = _create_mock_session(mock_db)
        mock_db.execute = AsyncMock(return_value=_mock_scalars([event]))

        mock_celery_task = MagicMock()
        mock_celery_task.delay = MagicMock()

        with patch("app.workers.outbox_publisher.get_session_factory", return_value=mock_factory):
            import app.workers.tasks as tasks_mod

            original = getattr(tasks_mod, "execute_background_task", None)
            tasks_mod.execute_background_task = mock_celery_task
            try:
                result = await publish_pending_outbox()
            finally:
                if original is not None:
                    tasks_mod.execute_background_task = original

            assert result == 1
            assert event.status == "published"
            assert event.published_at is not None
            mock_celery_task.delay.assert_called_once_with("task-1")

    @pytest.mark.asyncio
    async def test_publish_no_events(self):
        from app.workers.outbox_publisher import publish_pending_outbox

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_factory = _create_mock_session(mock_db)
        mock_db.execute = AsyncMock(return_value=_mock_scalars([]))

        with patch("app.workers.outbox_publisher.get_session_factory", return_value=mock_factory):
            result = await publish_pending_outbox()
            assert result == 0

    @pytest.mark.asyncio
    async def test_publish_event_failure_schedules_retry(self):
        from app.workers.outbox_publisher import publish_pending_outbox

        event = _make_outbox_event()
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_factory = _create_mock_session(mock_db)
        mock_db.execute = AsyncMock(return_value=_mock_scalars([event]))

        mock_celery_task = MagicMock()
        mock_celery_task.delay = MagicMock(side_effect=Exception("Celery down"))

        with patch("app.workers.outbox_publisher.get_session_factory", return_value=mock_factory):
            import app.workers.tasks as tasks_mod

            original = getattr(tasks_mod, "execute_background_task", None)
            tasks_mod.execute_background_task = mock_celery_task
            try:
                result = await publish_pending_outbox()
            finally:
                if original is not None:
                    tasks_mod.execute_background_task = original

            assert result == 0
            assert event.attempt_count == 1
            assert event.last_error == "Celery down"
            assert event.available_at is not None

    @pytest.mark.asyncio
    async def test_publish_event_permanent_failure(self):
        from app.workers.outbox_publisher import publish_pending_outbox

        event = _make_outbox_event(attempt_count=4, max_attempts=5)
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_factory = _create_mock_session(mock_db)
        mock_db.execute = AsyncMock(return_value=_mock_scalars([event]))

        mock_celery_task = MagicMock()
        mock_celery_task.delay = MagicMock(side_effect=Exception("Permanent failure"))

        with patch("app.workers.outbox_publisher.get_session_factory", return_value=mock_factory):
            import app.workers.tasks as tasks_mod

            original = getattr(tasks_mod, "execute_background_task", None)
            tasks_mod.execute_background_task = mock_celery_task
            try:
                result = await publish_pending_outbox()
            finally:
                if original is not None:
                    tasks_mod.execute_background_task = original

            assert result == 0
            assert event.status == "failed"
            assert event.attempt_count == 5

    @pytest.mark.asyncio
    async def test_publish_non_task_event_skipped(self):
        from app.workers.outbox_publisher import publish_pending_outbox

        event = _make_outbox_event(event_type="other.event", payload={"data": "test"})
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_factory = _create_mock_session(mock_db)
        mock_db.execute = AsyncMock(return_value=_mock_scalars([event]))

        with patch("app.workers.outbox_publisher.get_session_factory", return_value=mock_factory):
            result = await publish_pending_outbox()
            assert result == 1
            assert event.status == "published"

    @pytest.mark.asyncio
    async def test_publish_string_payload(self):
        from app.workers.outbox_publisher import publish_pending_outbox

        event = _make_outbox_event(payload='{"task_id": "task-1", "task_type": "test"}')
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_factory = _create_mock_session(mock_db)
        mock_db.execute = AsyncMock(return_value=_mock_scalars([event]))

        mock_celery_task = MagicMock()
        mock_celery_task.delay = MagicMock()

        with patch("app.workers.outbox_publisher.get_session_factory", return_value=mock_factory):
            import app.workers.tasks as tasks_mod

            original = getattr(tasks_mod, "execute_background_task", None)
            tasks_mod.execute_background_task = mock_celery_task
            try:
                result = await publish_pending_outbox()
            finally:
                if original is not None:
                    tasks_mod.execute_background_task = original

            assert result == 1
            mock_celery_task.delay.assert_called_once_with("task-1")
