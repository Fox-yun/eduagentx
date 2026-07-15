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
    t.agent_trace = overrides.get("agent_trace", [])
    return t


class TestRecordAgentStep:
    def test_appends_and_completes_same_agent_iteration(self):
        from app.workers.task_runtime import record_agent_step

        task = _make_task()
        record_agent_step(
            task,
            agent_key="content_generator",
            label="课程内容生成智能体",
            status="running",
            summary="生成中",
            artifact_type="课程内容",
        )
        record_agent_step(
            task,
            agent_key="content_generator",
            label="课程内容生成智能体",
            status="completed",
            summary="生成完成",
            artifact_type="课程内容",
        )

        assert len(task.agent_trace) == 1
        assert task.agent_trace[0]["status"] == "completed"
        assert task.agent_trace[0]["completed_at"] is not None

    def test_keeps_revision_iteration_as_separate_step(self):
        from app.workers.task_runtime import record_agent_step

        task = _make_task()
        for iteration in (1, 2):
            record_agent_step(
                task,
                agent_key="content_generator",
                label="课程内容生成智能体",
                status="completed",
                summary=f"第 {iteration} 轮",
                iteration=iteration,
            )

        assert [step["iteration"] for step in task.agent_trace] == [1, 2]


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
    async def test_recover_cancel_requested_unit_task_cleans_target(self):
        from app.workers.task_runtime import recover_stale_tasks

        db = AsyncMock()
        db.add = MagicMock()
        task = _make_task(
            status="cancel_requested",
            heartbeat_at=datetime(2020, 1, 1, tzinfo=UTC),
            next_event_sequence=4,
        )
        task.task_type = "learning_unit_generation"
        task.target_metadata = {"unit_content_version_id": "version-1"}

        version = MagicMock(status="generating")
        content = MagicMock(active_task_id=task.id, active_version_id=None)
        query_results = [
            _mock_scalars([task]),
            _mock_scalar_result(version),
            _mock_scalar_result(content),
        ]
        db.execute = AsyncMock(side_effect=query_results)

        result = await recover_stale_tasks(db)

        assert result == ["task-1"]
        assert task.status == "cancelled"
        assert task.next_event_sequence == 5
        assert version.status == "failed"
        assert version.error_code == "TASK_CANCELLED"
        assert content.active_task_id is None
        assert content.status == "failed"
        db.add.assert_called_once()
        db.commit.assert_awaited_once()

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
