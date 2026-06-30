"""Comprehensive unit tests for TaskService."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.errors import ApiError


def _mock_scalar_result(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _mock_scalars(items):
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


def _mock_scalar(value):
    r = MagicMock()
    r.scalar.return_value = value
    return r


def _make_task(**overrides):
    t = MagicMock()
    t.id = overrides.get("id", "task-1")
    t.user_id = overrides.get("user_id", "user-1")
    t.task_type = overrides.get("task_type", "learning_path_generation")
    t.status = overrides.get("status", "pending")
    t.progress = overrides.get("progress", 0)
    t.current_stage = overrides.get("current_stage")
    t.message = overrides.get("message")
    t.target_type = overrides.get("target_type", "goal")
    t.target_id = overrides.get("target_id", "goal-1")
    t.target_metadata = overrides.get("target_metadata")
    t.result = overrides.get("result")
    t.error_code = overrides.get("error_code")
    t.error_message = overrides.get("error_message")
    t.request_id = overrides.get("request_id")
    t.idempotency_key = overrides.get("idempotency_key")
    t.created_at = overrides.get("created_at", datetime.now(UTC))
    t.updated_at = overrides.get("updated_at", datetime.now(UTC))
    return t


class TestTaskServiceCreateTask:
    @pytest.mark.asyncio
    async def test_create_task_happy_path(self):
        from app.services.task import TaskService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = TaskService(db)
        db.execute = AsyncMock(return_value=_mock_scalar_result(None))

        task = await svc.create_task(
            user_id="user-1",
            task_type="learning_path_generation",
            target_type="goal",
            target_id="goal-1",
        )
        assert task is not None
        db.add.assert_called()
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_create_task_idempotent(self):
        from app.services.task import TaskService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = TaskService(db)
        existing = _make_task(id="existing-task")
        db.execute = AsyncMock(return_value=_mock_scalar_result(existing))

        task = await svc.create_task(
            user_id="user-1",
            task_type="learning_path_generation",
            idempotency_key="key-123",
        )
        assert task.id == "existing-task"

    @pytest.mark.asyncio
    async def test_create_task_with_metadata(self):
        from app.services.task import TaskService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = TaskService(db)
        db.execute = AsyncMock(return_value=_mock_scalar_result(None))

        task = await svc.create_task(
            user_id="user-1",
            task_type="learning_unit_generation",
            target_type="node",
            target_id="node-1",
            target_metadata={"path_id": "path-1"},
            request_id="req-1",
        )
        assert task is not None


class TestTaskServiceGetTask:
    @pytest.mark.asyncio
    async def test_get_task_found(self):
        from app.services.task import TaskService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = TaskService(db)
        task = _make_task()
        db.execute = AsyncMock(return_value=_mock_scalar_result(task))

        result = await svc.get_task("task-1", "user-1")
        assert result is task

    @pytest.mark.asyncio
    async def test_get_task_not_found(self):
        from app.services.task import TaskService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = TaskService(db)
        db.execute = AsyncMock(return_value=_mock_scalar_result(None))

        with pytest.raises(ApiError) as exc_info:
            await svc.get_task("nonexistent", "user-1")
        assert exc_info.value.code == "TASK_NOT_FOUND"


class TestTaskServiceListTasks:
    @pytest.mark.asyncio
    async def test_list_tasks_empty(self):
        from app.services.task import TaskService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = TaskService(db)

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar(0)
            elif call_count == 2:
                return _mock_scalars([])
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await svc.list_tasks("user-1")
        assert result["items"] == []
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_list_tasks_with_items(self):
        from app.services.task import TaskService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = TaskService(db)
        tasks = [_make_task(id=f"t{i}") for i in range(3)]

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar(3)
            elif call_count == 2:
                return _mock_scalars(tasks)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await svc.list_tasks("user-1")
        assert len(result["items"]) == 3
        assert result["next_cursor"] is None

    @pytest.mark.asyncio
    async def test_list_tasks_with_pagination(self):
        from app.services.task import TaskService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = TaskService(db)
        tasks = [_make_task(id=f"t{i}", created_at=datetime.now(UTC)) for i in range(21)]

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar(30)
            elif call_count == 2:
                return _mock_scalars(tasks)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await svc.list_tasks("user-1", limit=20)
        assert len(result["items"]) == 20
        assert result["next_cursor"] is not None


class TestTaskServiceUpdateTaskStatus:
    @pytest.mark.asyncio
    async def test_update_status_not_found(self):
        from app.services.task import TaskService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = TaskService(db)
        db.execute = AsyncMock(return_value=_mock_scalar_result(None))

        with pytest.raises(ApiError) as exc_info:
            await svc.update_task_status("bad-task", "running")
        assert exc_info.value.code == "TASK_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_update_status_invalid_transition(self):
        from app.services.task import TaskService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = TaskService(db)
        task = _make_task(status="completed")  # terminal
        db.execute = AsyncMock(return_value=_mock_scalar_result(task))

        with pytest.raises(ApiError) as exc_info:
            await svc.update_task_status("task-1", "running")
        assert exc_info.value.code == "INVALID_TRANSITION"

    @pytest.mark.asyncio
    async def test_update_status_delegates_to_runtime(self):
        from app.services.task import TaskService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = TaskService(db)
        task = _make_task(status="pending")

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(task)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with patch(
            "app.workers.task_runtime.update_task_status", new_callable=AsyncMock, return_value=task
        ) as mock_runtime:
            result = await svc.update_task_status("task-1", "running", progress=50, stage="analyzing")
            mock_runtime.assert_awaited_once()
            assert result is task


class TestTaskServiceCancelTask:
    @pytest.mark.asyncio
    async def test_cancel_pending_task(self):
        from app.services.task import TaskService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = TaskService(db)
        task = _make_task(status="pending")

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(task)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with patch.object(svc, "update_task_status", new_callable=AsyncMock, return_value=task) as mock_update:
            await svc.cancel_task("task-1", "user-1")
            mock_update.assert_awaited_once_with("task-1", "cancelled", message="任务已取消")

    @pytest.mark.asyncio
    async def test_cancel_running_task(self):
        from app.services.task import TaskService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = TaskService(db)
        task = _make_task(status="running")

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(task)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with patch.object(svc, "update_task_status", new_callable=AsyncMock, return_value=task) as mock_update:
            await svc.cancel_task("task-1", "user-1")
            mock_update.assert_awaited_once_with("task-1", "cancel_requested", message="正在取消...")

    @pytest.mark.asyncio
    async def test_cancel_completed_task_raises(self):
        from app.services.task import TaskService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = TaskService(db)
        task = _make_task(status="completed")

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(task)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with pytest.raises(ApiError) as exc_info:
            await svc.cancel_task("task-1", "user-1")
        assert exc_info.value.code == "TASK_ALREADY_COMPLETED"


class TestTaskServiceGetTaskEvents:
    @pytest.mark.asyncio
    async def test_get_events(self):
        from app.services.task import TaskService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = TaskService(db)
        events = [MagicMock(), MagicMock()]
        db.execute = AsyncMock(return_value=_mock_scalars(events))

        result = await svc.get_task_events("task-1")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_events_after_sequence(self):
        from app.services.task import TaskService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = TaskService(db)
        events = [MagicMock()]
        db.execute = AsyncMock(return_value=_mock_scalars(events))

        result = await svc.get_task_events("task-1", after_sequence=5)
        assert len(result) == 1


class TestTaskServiceStatusToEventType:
    def test_status_mapping(self):
        from app.services.task import TaskService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = TaskService(db)
        assert svc._status_to_event_type("pending") == "snapshot"
        assert svc._status_to_event_type("running") == "progress"
        assert svc._status_to_event_type("completed") == "completed"
        assert svc._status_to_event_type("failed") == "failed"
        assert svc._status_to_event_type("cancelled") == "cancelled"
        assert svc._status_to_event_type("unknown") == "progress"
