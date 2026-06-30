"""Comprehensive unit tests for SSE stream endpoint in tasks router.

Covers: stream_task_events, Last-Event-ID parsing, SSE event generation,
terminal state close, get_task_events with after_sequence filter.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import ApiError


def _make_task(**overrides):
    t = MagicMock()
    t.id = overrides.get("id", "task-1")
    t.user_id = overrides.get("user_id", "user-1")
    t.task_type = overrides.get("task_type", "learning_path_generation")
    t.status = overrides.get("status", "running")
    t.progress = overrides.get("progress", 0)
    t.current_stage = overrides.get("current_stage")
    t.message = overrides.get("message", "Task created")
    t.result = overrides.get("result")
    t.error_message = overrides.get("error_message")
    t.request_id = overrides.get("request_id")
    t.created_at = overrides.get("created_at", datetime.now(UTC))
    t.updated_at = overrides.get("updated_at", datetime.now(UTC))
    return t


def _make_event(**overrides):
    e = MagicMock()
    e.task_id = overrides.get("task_id", "task-1")
    e.sequence_number = overrides.get("sequence_number", 0)
    e.event_type = overrides.get("event_type", "snapshot")
    e.status = overrides.get("status", "running")
    e.progress = overrides.get("progress", 50)
    e.stage = overrides.get("stage")
    e.message = overrides.get("message", "Progress update")
    e.result = overrides.get("result")
    e.created_at = overrides.get("created_at", datetime.now(UTC))
    return e


@pytest.fixture
def stream_app():
    """Create a FastAPI app with mocked auth and DB for SSE testing."""
    app = FastAPI()
    from app.core.errors import register_error_handlers

    register_error_handlers(app)

    mock_user = MagicMock()
    mock_user.id = "user-1"

    from app.routers.tasks import router

    app.include_router(router, prefix="/tasks")

    from app.core.auth_deps import require_learning_user

    async def override_auth():
        return mock_user

    from app.core.database import get_db

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.add_all = MagicMock()
    mock_db.add = MagicMock()
    mock_db.add_all = MagicMock()
    mock_db.close = AsyncMock()

    async def override_db():
        return mock_db

    app.dependency_overrides[require_learning_user] = override_auth
    app.dependency_overrides[get_db] = override_db

    return app, mock_db


class TestStreamTaskEvents:
    """Test the SSE stream endpoint."""

    def test_stream_returns_event_stream_content_type(self, stream_app):
        app, mock_db = stream_app
        task = _make_task(status="completed")
        event = _make_event(status="completed", progress=100)

        mock_gen_db = AsyncMock()
        mock_gen_db.add = MagicMock()
        mock_gen_db.add_all = MagicMock()
        mock_gen_db.add = MagicMock()
        mock_gen_db.add_all = MagicMock()
        mock_factory = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_gen_db), __aexit__=AsyncMock(return_value=False)
            )
        )

        with (
            patch("app.routers.tasks.TaskService") as MockSvc,
            patch("app.core.database.get_session_factory", return_value=mock_factory),
        ):
            instance = MockSvc.return_value
            instance.get_task = AsyncMock(return_value=task)
            instance.get_task_events = AsyncMock(return_value=[event])

            client = TestClient(app)
            resp = client.get("/tasks/task-1/stream")
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]

    def test_stream_sends_missed_events(self, stream_app):
        app, mock_db = stream_app
        task = _make_task(status="completed")
        event0 = _make_event(sequence_number=0, status="running", progress=30)
        event1 = _make_event(sequence_number=1, status="completed", progress=100)

        mock_gen_db = AsyncMock()
        mock_gen_db.add = MagicMock()
        mock_gen_db.add_all = MagicMock()
        mock_gen_db.add = MagicMock()
        mock_gen_db.add_all = MagicMock()
        mock_factory = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_gen_db), __aexit__=AsyncMock(return_value=False)
            )
        )

        with (
            patch("app.routers.tasks.TaskService") as MockSvc,
            patch("app.core.database.get_session_factory", return_value=mock_factory),
        ):
            instance = MockSvc.return_value
            instance.get_task = AsyncMock(return_value=task)
            instance.get_task_events = AsyncMock(return_value=[event0, event1])

            client = TestClient(app)
            resp = client.get("/tasks/task-1/stream")
            text = resp.text
            blocks = text.strip().split("\n\n")
            # Should have at least 2 data events
            data_events = [b for b in blocks if "data:" in b]
            assert len(data_events) == 2, f"Expected 2 events, got {len(data_events)}. Response: {text!r}"

            first = json.loads(data_events[0].split("data:", 1)[1].strip())
            assert first["status"] == "running"
            assert first["progress"] == 30

    def test_stream_closes_on_terminal_event(self, stream_app):
        """When the only missed event is terminal, stream closes immediately."""
        app, mock_db = stream_app
        task = _make_task(status="completed")
        terminal_event = _make_event(status="completed", progress=100, sequence_number=5)

        mock_gen_db = AsyncMock()
        mock_gen_db.add = MagicMock()
        mock_gen_db.add_all = MagicMock()
        mock_gen_db.add = MagicMock()
        mock_gen_db.add_all = MagicMock()
        mock_factory = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_gen_db), __aexit__=AsyncMock(return_value=False)
            )
        )

        with (
            patch("app.routers.tasks.TaskService") as MockSvc,
            patch("app.core.database.get_session_factory", return_value=mock_factory),
        ):
            instance = MockSvc.return_value
            instance.get_task = AsyncMock(return_value=task)
            instance.get_task_events = AsyncMock(return_value=[terminal_event])

            client = TestClient(app)
            resp = client.get("/tasks/task-1/stream")
            # Should have exactly one event and then close
            data_lines = [ln for ln in resp.text.split("\n") if ln.startswith("data:")]
            assert len(data_lines) == 1

    def test_stream_no_events_enters_polling(self, stream_app):
        """When no missed events, stream enters polling loop and exits on terminal event."""
        app, mock_db = stream_app
        task = _make_task(status="completed")

        mock_gen_db = AsyncMock()
        mock_gen_db.add = MagicMock()
        mock_gen_db.add_all = MagicMock()
        mock_gen_db.add = MagicMock()
        mock_gen_db.add_all = MagicMock()
        # Mock gen_db.execute to return a result with scalar_one_or_none
        mock_exec_result = MagicMock()
        mock_exec_result.scalar_one_or_none.return_value = task
        mock_gen_db.execute = AsyncMock(return_value=mock_exec_result)

        mock_factory = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_gen_db), __aexit__=AsyncMock(return_value=False)
            )
        )

        poll_count = 0

        async def mock_get_events(tid, after_seq=None):
            nonlocal poll_count
            poll_count += 1
            # After a few polls, return a terminal event to close the stream
            if poll_count >= 4:
                return [_make_event(status="completed", progress=100, sequence_number=1)]
            return []

        with (
            patch("app.routers.tasks.TaskService") as MockSvc,
            patch("app.core.database.get_session_factory", return_value=mock_factory),
            patch("app.routers.tasks.asyncio.sleep", new_callable=AsyncMock),
        ):
            instance = MockSvc.return_value
            instance.get_task = AsyncMock(return_value=task)
            instance.get_task_events = AsyncMock(side_effect=mock_get_events)

            client = TestClient(app)
            resp = client.get("/tasks/task-1/stream")
            assert resp.status_code == 200
            # Polled multiple times before getting terminal event
            assert poll_count >= 4

    def test_stream_sends_heartbeat(self, stream_app):
        """After 15 polls, a heartbeat comment is sent before a terminal event closes the stream."""
        app, mock_db = stream_app
        task = _make_task(status="completed")

        mock_gen_db = AsyncMock()
        mock_gen_db.add = MagicMock()
        mock_gen_db.add_all = MagicMock()
        mock_gen_db.add = MagicMock()
        mock_gen_db.add_all = MagicMock()
        mock_exec_result = MagicMock()
        mock_exec_result.scalar_one_or_none.return_value = task
        mock_gen_db.execute = AsyncMock(return_value=mock_exec_result)

        mock_factory = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_gen_db), __aexit__=AsyncMock(return_value=False)
            )
        )

        poll_count = 0

        async def mock_get_events(tid, after_seq=None):
            nonlocal poll_count
            poll_count += 1
            # After 15+ polls (heartbeat was sent), return terminal event to close
            if poll_count >= 16:
                return [_make_event(status="completed", progress=100, sequence_number=1)]
            return []

        with (
            patch("app.routers.tasks.TaskService") as MockSvc,
            patch("app.core.database.get_session_factory", return_value=mock_factory),
            patch("app.routers.tasks.asyncio.sleep", new_callable=AsyncMock),
        ):
            instance = MockSvc.return_value
            instance.get_task = AsyncMock(return_value=task)
            instance.get_task_events = AsyncMock(side_effect=mock_get_events)

            client = TestClient(app)
            resp = client.get("/tasks/task-1/stream")
            # Should contain heartbeat comments (every 15 polls)
            assert ": heartbeat" in resp.text
            assert poll_count >= 16


class TestLastEventIdParsing:
    """Test Last-Event-ID header parsing in the SSE endpoint."""

    def test_last_event_id_replays_missed_events(self, stream_app):
        """With Last-Event-ID header, only events after that sequence are sent."""
        app, mock_db = stream_app
        task = _make_task(status="completed")
        # Only return events after sequence 2
        event3 = _make_event(sequence_number=3, status="running", progress=70)
        event4 = _make_event(sequence_number=4, status="completed", progress=100)

        mock_gen_db = AsyncMock()
        mock_gen_db.add = MagicMock()
        mock_gen_db.add_all = MagicMock()
        mock_gen_db.add = MagicMock()
        mock_gen_db.add_all = MagicMock()
        mock_factory = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_gen_db), __aexit__=AsyncMock(return_value=False)
            )
        )

        with (
            patch("app.routers.tasks.TaskService") as MockSvc,
            patch("app.core.database.get_session_factory", return_value=mock_factory),
        ):
            instance = MockSvc.return_value
            instance.get_task = AsyncMock(return_value=task)
            instance.get_task_events = AsyncMock(return_value=[event3, event4])

            client = TestClient(app)
            resp = client.get("/tasks/task-1/stream", headers={"Last-Event-ID": "task-1:2"})
            assert resp.status_code == 200

            # Verify get_task_events was called with after_sequence=2
            instance.get_task_events.assert_called_once_with("task-1", 2)

    def test_last_event_id_ignored_for_wrong_task(self, stream_app):
        """Last-Event-ID with wrong task_id is ignored (after_sequence=None)."""
        app, mock_db = stream_app
        task = _make_task(status="completed")
        event = _make_event(status="completed", progress=100)

        mock_gen_db = AsyncMock()
        mock_gen_db.add = MagicMock()
        mock_gen_db.add_all = MagicMock()
        mock_gen_db.add = MagicMock()
        mock_gen_db.add_all = MagicMock()
        mock_factory = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_gen_db), __aexit__=AsyncMock(return_value=False)
            )
        )

        with (
            patch("app.routers.tasks.TaskService") as MockSvc,
            patch("app.core.database.get_session_factory", return_value=mock_factory),
        ):
            instance = MockSvc.return_value
            instance.get_task = AsyncMock(return_value=task)
            instance.get_task_events = AsyncMock(return_value=[event])

            client = TestClient(app)
            resp = client.get(
                "/tasks/task-1/stream",
                headers={"Last-Event-ID": "other-task:5"},
            )
            assert resp.status_code == 200
            # Should be called with None (no after_sequence filter)
            instance.get_task_events.assert_called_once_with("task-1", None)

    def test_last_event_id_malformat_ignored(self, stream_app):
        """Malformed Last-Event-ID is silently ignored."""
        app, mock_db = stream_app
        task = _make_task(status="completed")
        event = _make_event(status="completed", progress=100)

        mock_gen_db = AsyncMock()
        mock_gen_db.add = MagicMock()
        mock_gen_db.add_all = MagicMock()
        mock_gen_db.add = MagicMock()
        mock_gen_db.add_all = MagicMock()
        mock_factory = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_gen_db), __aexit__=AsyncMock(return_value=False)
            )
        )

        with (
            patch("app.routers.tasks.TaskService") as MockSvc,
            patch("app.core.database.get_session_factory", return_value=mock_factory),
        ):
            instance = MockSvc.return_value
            instance.get_task = AsyncMock(return_value=task)
            instance.get_task_events = AsyncMock(return_value=[event])

            client = TestClient(app)
            # Various malformed formats
            for bad_id in ["not-a-uuid", "task-1:abc", "task-1:-1", ":5", ""]:
                instance.get_task_events.reset_mock()
                resp = client.get(
                    "/tasks/task-1/stream",
                    headers={"Last-Event-ID": bad_id},
                )
                assert resp.status_code == 200
                # All should be treated as no after_sequence
                instance.get_task_events.assert_called_once_with("task-1", None)

    def test_last_event_id_negative_sequence_ignored(self, stream_app):
        """Negative sequence number in Last-Event-ID is ignored."""
        app, mock_db = stream_app
        task = _make_task(status="completed")
        event = _make_event(status="completed", progress=100)

        mock_gen_db = AsyncMock()
        mock_gen_db.add = MagicMock()
        mock_gen_db.add_all = MagicMock()
        mock_gen_db.add = MagicMock()
        mock_gen_db.add_all = MagicMock()
        mock_factory = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_gen_db), __aexit__=AsyncMock(return_value=False)
            )
        )

        with (
            patch("app.routers.tasks.TaskService") as MockSvc,
            patch("app.core.database.get_session_factory", return_value=mock_factory),
        ):
            instance = MockSvc.return_value
            instance.get_task = AsyncMock(return_value=task)
            instance.get_task_events = AsyncMock(return_value=[event])

            client = TestClient(app)
            resp = client.get(
                "/tasks/task-1/stream",
                headers={"Last-Event-ID": "task-1:-1"},
            )
            assert resp.status_code == 200
            # -1 < 0, so after_sequence stays None
            instance.get_task_events.assert_called_once_with("task-1", None)


class TestGetTaskEventsWithAfterSequence:
    """Test TaskService.get_task_events with after_sequence filter."""

    @pytest.mark.asyncio
    async def test_get_all_events_when_no_filter(self):
        from app.services.task import TaskService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = TaskService(db)

        event0 = _make_event(sequence_number=0)
        event1 = _make_event(sequence_number=1)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [event0, event1]
        db.execute = AsyncMock(return_value=mock_result)

        events = await svc.get_task_events("task-1")
        assert len(events) == 2
        assert events[0].sequence_number == 0
        assert events[1].sequence_number == 1

    @pytest.mark.asyncio
    async def test_get_events_after_sequence(self):
        from app.services.task import TaskService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = TaskService(db)

        event3 = _make_event(sequence_number=3)
        event4 = _make_event(sequence_number=4)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [event3, event4]
        db.execute = AsyncMock(return_value=mock_result)

        events = await svc.get_task_events("task-1", after_sequence=2)
        assert len(events) == 2
        assert events[0].sequence_number == 3

    @pytest.mark.asyncio
    async def test_get_events_empty_result(self):
        from app.services.task import TaskService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = TaskService(db)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        events = await svc.get_task_events("task-1", after_sequence=100)
        assert events == []


class TestStreamOwnershipCheck:
    """Test that the stream endpoint verifies task ownership."""

    def test_stream_task_not_found(self, stream_app):
        app, mock_db = stream_app

        with patch("app.routers.tasks.TaskService") as MockSvc:
            instance = MockSvc.return_value
            instance.get_task = AsyncMock(
                side_effect=ApiError(code="TASK_NOT_FOUND", message="Not found", status_code=404)
            )

            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/tasks/nonexistent/stream")
            assert resp.status_code == 404


class TestStreamEventFormat:
    """Test SSE event format correctness."""

    def test_event_id_format_in_sse(self, stream_app):
        """Verify SSE events have correct id: and data: format."""
        app, mock_db = stream_app
        task = _make_task(status="completed")
        event = _make_event(
            sequence_number=7,
            status="completed",
            progress=100,
            event_type="status_change",
            stage="review",
        )

        mock_gen_db = AsyncMock()
        mock_gen_db.add = MagicMock()
        mock_gen_db.add_all = MagicMock()
        mock_gen_db.add = MagicMock()
        mock_gen_db.add_all = MagicMock()
        mock_factory = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_gen_db), __aexit__=AsyncMock(return_value=False)
            )
        )

        with (
            patch("app.routers.tasks.TaskService") as MockSvc,
            patch("app.core.database.get_session_factory", return_value=mock_factory),
        ):
            instance = MockSvc.return_value
            instance.get_task = AsyncMock(return_value=task)
            instance.get_task_events = AsyncMock(return_value=[event])

            client = TestClient(app)
            resp = client.get("/tasks/task-1/stream")

            # Parse the SSE output
            lines = resp.text.split("\n")
            id_lines = [ln for ln in lines if ln.startswith("id:")]
            data_lines = [ln for ln in lines if ln.startswith("data:")]

            assert len(id_lines) == 1
            assert "task-1:7" in id_lines[0]

            assert len(data_lines) == 1
            data = json.loads(data_lines[0].split("data:", 1)[1].strip())
            assert data["event_id"] == "task-1:7"
            assert data["status"] == "completed"
            assert data["progress"] == 100
            assert data["stage"] == "review"
            assert data["type"] == "status_change"
