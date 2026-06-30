"""Comprehensive unit tests for task_runtime module."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest


def _mock_scalar_result(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _mock_scalars(items):
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


def _make_task(**overrides):
    t = MagicMock()
    t.id = overrides.get("id", "task-1")
    t.status = overrides.get("status", "pending")
    t.progress = overrides.get("progress", 0)
    t.current_stage = overrides.get("current_stage")
    t.message = overrides.get("message")
    t.result = overrides.get("result")
    t.error_code = overrides.get("error_code")
    t.error_message = overrides.get("error_message")
    t.retry_count = overrides.get("retry_count", 0)
    t.max_retries = overrides.get("max_retries", 3)
    t.heartbeat_at = overrides.get("heartbeat_at", datetime.now(UTC))
    t.next_event_sequence = overrides.get("next_event_sequence", 1)
    return t


class TestUpdateTaskStatus:
    @pytest.mark.asyncio
    async def test_update_status_running(self):
        from app.workers.task_runtime import update_task_status

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        task = _make_task(status="pending")

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # select task
                return _mock_scalar_result(task)
            elif call_count == 2:  # update sequence returning
                mock = MagicMock()
                mock.scalar_one.return_value = 2  # next_sequence = 2
                return mock
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await update_task_status(db, "task-1", "running", progress=10, stage="analyzing", message="Starting")
        assert result.status == "running"
        assert result.progress == 10
        assert result.current_stage == "analyzing"
        assert result.started_at is not None
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_update_status_completed(self):
        from app.workers.task_runtime import update_task_status

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        task = _make_task(status="running")

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(task)
            elif call_count == 2:
                mock = MagicMock()
                mock.scalar_one.return_value = 2
                return mock
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await update_task_status(db, "task-1", "completed", progress=100, result={"data": "ok"})
        assert result.status == "completed"
        assert result.completed_at is not None
        assert result.result == {"data": "ok"}

    @pytest.mark.asyncio
    async def test_update_status_failed(self):
        from app.workers.task_runtime import update_task_status

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        task = _make_task(status="running")

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(task)
            elif call_count == 2:
                mock = MagicMock()
                mock.scalar_one.return_value = 2
                return mock
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await update_task_status(db, "task-1", "failed", error_code="ERR", error_message="Something broke")
        assert result.status == "failed"
        assert result.error_code == "ERR"
        assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_update_status_not_found(self):
        from app.workers.task_runtime import update_task_status

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.execute = AsyncMock(return_value=_mock_scalar_result(None))

        with pytest.raises(ValueError):
            await update_task_status(db, "bad-task", "running")

    @pytest.mark.asyncio
    async def test_update_status_with_partial_fields(self):
        from app.workers.task_runtime import update_task_status

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        task = _make_task(status="pending", progress=0, current_stage=None, message=None)

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(task)
            elif call_count == 2:
                mock = MagicMock()
                mock.scalar_one.return_value = 2
                return mock
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await update_task_status(db, "task-1", "running")
        assert result.status == "running"
        # Fields not passed should not be updated
        assert result.progress == 0

    @pytest.mark.asyncio
    async def test_update_status_cancel_requested(self):
        from app.workers.task_runtime import update_task_status

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        task = _make_task(status="running")

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(task)
            elif call_count == 2:
                mock = MagicMock()
                mock.scalar_one.return_value = 2
                return mock
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await update_task_status(db, "task-1", "cancel_requested", message="Cancelling...")
        assert result.status == "cancel_requested"


class TestStatusToEventType:
    def test_all_status_mappings(self):
        from app.workers.task_runtime import _status_to_event_type

        assert _status_to_event_type("pending") == "snapshot"
        assert _status_to_event_type("running") == "progress"
        assert _status_to_event_type("completed") == "completed"
        assert _status_to_event_type("partial_completed") == "partial_completed"
        assert _status_to_event_type("failed") == "failed"
        assert _status_to_event_type("cancelled") == "cancelled"
        assert _status_to_event_type("cancel_requested") == "progress"
        assert _status_to_event_type("unknown_status") == "progress"


class TestRecoverStaleTasks:
    @pytest.mark.asyncio
    async def test_recover_retryable_tasks(self):
        from app.workers.task_runtime import recover_stale_tasks

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        task = _make_task(status="running", retry_count=1, max_retries=3)
        db.execute = AsyncMock(return_value=_mock_scalars([task]))

        result = await recover_stale_tasks(db)
        assert task.status == "interrupted"
        assert task.retry_count == 2
        assert "task-1" in result
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_recover_max_retries_exceeded(self):
        from app.workers.task_runtime import recover_stale_tasks

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        task = _make_task(status="running", retry_count=3, max_retries=3)
        db.execute = AsyncMock(return_value=_mock_scalars([task]))

        result = await recover_stale_tasks(db)
        assert task.status == "failed"
        assert task.error_code == "MAX_RETRIES_EXCEEDED"
        assert result == []

    @pytest.mark.asyncio
    async def test_recover_no_stale_tasks(self):
        from app.workers.task_runtime import recover_stale_tasks

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.execute = AsyncMock(return_value=_mock_scalars([]))

        result = await recover_stale_tasks(db)
        assert result == []
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_recover_multiple_tasks(self):
        from app.workers.task_runtime import recover_stale_tasks

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        task1 = _make_task(id="t1", retry_count=0, max_retries=3)
        task2 = _make_task(id="t2", retry_count=3, max_retries=3)
        task3 = _make_task(id="t3", retry_count=2, max_retries=3)
        db.execute = AsyncMock(return_value=_mock_scalars([task1, task2, task3]))

        result = await recover_stale_tasks(db)
        assert "t1" in result
        assert "t3" in result
        assert "t2" not in result
        assert task2.status == "failed"
