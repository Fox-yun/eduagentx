"""Comprehensive unit tests for tasks router endpoints."""

from __future__ import annotations

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
    t.status = overrides.get("status", "pending")
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
    e.status = overrides.get("status", "pending")
    e.progress = overrides.get("progress", 0)
    e.stage = overrides.get("stage")
    e.message = overrides.get("message", "Started")
    e.result = overrides.get("result")
    e.created_at = overrides.get("created_at", datetime.now(UTC))
    return e


@pytest.fixture
def app_with_mocked_auth():
    """Create a FastAPI app with mocked auth dependency."""
    app = FastAPI()

    # Register error handlers so ApiError returns proper status codes
    from app.core.errors import register_error_handlers

    register_error_handlers(app)

    mock_user = MagicMock()
    mock_user.id = "user-1"

    from app.routers.tasks import router

    app.include_router(router, prefix="/tasks")

    # Override auth dependency
    from app.core.auth_deps import require_learning_user

    async def override_auth():
        return mock_user

    from app.core.database import get_db

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.add_all = MagicMock()
    mock_db.add = MagicMock()
    mock_db.add_all = MagicMock()

    async def override_db():
        return mock_db

    app.dependency_overrides[require_learning_user] = override_auth
    app.dependency_overrides[get_db] = override_db

    return app, mock_db


class TestTasksRouterListTasks:
    def test_list_tasks(self, app_with_mocked_auth):
        app, mock_db = app_with_mocked_auth

        task = _make_task()

        with patch("app.routers.tasks.TaskService") as MockService:
            instance = MockService.return_value
            instance.list_tasks = AsyncMock(
                return_value={
                    "items": [task],
                    "next_cursor": None,
                    "total": 1,
                }
            )

            client = TestClient(app)
            resp = client.get("/tasks")
            assert resp.status_code == 200
            data = resp.json()
            assert "items" in data
            assert data["total"] == 1


class TestTasksRouterGetTask:
    def test_get_task(self, app_with_mocked_auth):
        app, mock_db = app_with_mocked_auth

        task = _make_task()

        with patch("app.routers.tasks.TaskService") as MockService:
            instance = MockService.return_value
            instance.get_task = AsyncMock(return_value=task)

            client = TestClient(app)
            resp = client.get("/tasks/task-1")
            assert resp.status_code == 200
            data = resp.json()
            assert data["task_id"] == "task-1"

    def test_get_task_not_found(self, app_with_mocked_auth):
        app, mock_db = app_with_mocked_auth

        with patch("app.routers.tasks.TaskService") as MockService:
            instance = MockService.return_value
            instance.get_task = AsyncMock(
                side_effect=ApiError(code="TASK_NOT_FOUND", message="Not found", status_code=404)
            )

            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/tasks/nonexistent")
            assert resp.status_code == 404


class TestTasksRouterCancelTask:
    def test_cancel_task(self, app_with_mocked_auth):
        app, mock_db = app_with_mocked_auth

        task = _make_task(status="cancelled")

        with patch("app.routers.tasks.TaskService") as MockService:
            instance = MockService.return_value
            instance.cancel_task = AsyncMock(return_value=task)

            client = TestClient(app)
            resp = client.post("/tasks/task-1/cancel")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "cancelled"


class TestTaskToDict:
    def test_task_to_dict(self):
        from app.routers.tasks import _task_to_dict

        task = _make_task()
        result = _task_to_dict(task)
        assert result["task_id"] == "task-1"
        assert result["type"] == "learning_path_generation"
        assert result["status"] == "pending"
        assert "created_at" in result


class TestEventToSse:
    def test_event_to_sse(self):
        from app.routers.tasks import _event_to_sse

        event = _make_event()
        result = _event_to_sse(event)
        assert result["event_id"] == "task-1:0"
        assert result["task_id"] == "task-1"
        assert result["type"] == "snapshot"
