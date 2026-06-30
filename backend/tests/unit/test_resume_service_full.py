"""Comprehensive unit tests for ResumeService."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest


def _mock_scalar_result(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _mock_scalar(value):
    r = MagicMock()
    r.scalar.return_value = value
    return r


def _mock_scalars(items):
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


def _make_goal(**overrides):
    g = MagicMock()
    g.id = overrides.get("id", "goal-1")
    g.user_id = overrides.get("user_id", "user-1")
    g.title = overrides.get("title", "Learn Python")
    g.status = overrides.get("status", "active")
    g.active_task_id = overrides.get("active_task_id")
    g.current_path_id = overrides.get("current_path_id", "path-1")
    g.created_at = overrides.get("created_at", datetime.now(UTC))
    g.updated_at = overrides.get("updated_at", datetime.now(UTC))
    return g


class TestResumeServiceGetResume:
    @pytest.mark.asyncio
    async def test_empty_when_no_goal(self):
        from app.services.resume import ResumeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = ResumeService(db)
        db.execute = AsyncMock(return_value=_mock_scalar_result(None))

        result = await svc.get_resume("user-1")
        assert result["type"] == "empty"

    @pytest.mark.asyncio
    async def test_generating_state(self):
        from app.services.resume import ResumeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = ResumeService(db)
        goal = _make_goal(status="planning", active_task_id="task-1")
        db.execute = AsyncMock(return_value=_mock_scalar_result(goal))

        result = await svc.get_resume("user-1")
        assert result["type"] == "generating"
        assert result["task_id"] == "task-1"
        assert result["goal_id"] == "goal-1"

    @pytest.mark.asyncio
    async def test_generating_clarifying_state(self):
        from app.services.resume import ResumeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = ResumeService(db)
        goal = _make_goal(status="clarifying", active_task_id="task-2")
        db.execute = AsyncMock(return_value=_mock_scalar_result(goal))

        result = await svc.get_resume("user-1")
        assert result["type"] == "generating"
        assert result["stage"] == "目标澄清"

    @pytest.mark.asyncio
    async def test_generating_diagnosing_state(self):
        from app.services.resume import ResumeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = ResumeService(db)
        goal = _make_goal(status="diagnosing", active_task_id="task-3")
        db.execute = AsyncMock(return_value=_mock_scalar_result(goal))

        result = await svc.get_resume("user-1")
        assert result["type"] == "generating"
        assert result["stage"] == "能力诊断"

    @pytest.mark.asyncio
    async def test_review_state(self):
        from app.services.resume import ResumeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = ResumeService(db)
        goal = _make_goal(status="ready", current_path_id="path-1")
        path = MagicMock()
        path.active_version_id = "ver-1"

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # goal query
                return _mock_scalar_result(goal)
            elif call_count == 2:  # path stats: path query
                return _mock_scalar_result(path)
            elif call_count == 3:  # total nodes
                return _mock_scalar(5)
            elif call_count == 4:  # completed nodes
                return _mock_scalar(0)
            elif call_count == 5:  # estimated minutes
                return _mock_scalar(150)
            elif call_count == 6:  # nodes for current
                return _mock_scalars([])
            elif call_count == 7:  # mastery
                return _mock_scalar(0)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await svc.get_resume("user-1")
        assert result["type"] == "review"
        assert result["path_id"] == "path-1"

    @pytest.mark.asyncio
    async def test_active_state(self):
        from app.services.resume import ResumeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = ResumeService(db)
        goal = _make_goal(status="active", current_path_id="path-1")
        path = MagicMock()
        path.active_version_id = "ver-1"

        node = MagicMock()
        node.id = "node-1"
        node.title = "Basics"
        prog = MagicMock()
        prog.status = "in_progress"

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # goal
                return _mock_scalar_result(goal)
            elif call_count == 2:  # path
                return _mock_scalar_result(path)
            elif call_count == 3:  # total nodes
                return _mock_scalar(10)
            elif call_count == 4:  # completed nodes
                return _mock_scalar(3)
            elif call_count == 5:  # estimated minutes
                return _mock_scalar(300)
            elif call_count == 6:  # nodes
                return _mock_scalars([node])
            elif call_count == 7:  # progress for node
                return _mock_scalar_result(prog)
            elif call_count == 8:  # mastery
                return _mock_scalar(45.5)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await svc.get_resume("user-1")
        assert result["type"] == "active"
        assert result["current_node_id"] == "node-1"
        assert result["completed_nodes"] == 3
        assert result["total_nodes"] == 10

    @pytest.mark.asyncio
    async def test_completed_state(self):
        from app.services.resume import ResumeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = ResumeService(db)
        goal = _make_goal(status="completed", current_path_id="path-1")
        path = MagicMock()
        path.active_version_id = "ver-1"

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # goal
                return _mock_scalar_result(goal)
            elif call_count == 2:  # path
                return _mock_scalar_result(path)
            elif call_count == 3 or call_count == 4:  # total nodes
                return _mock_scalar(5)
            elif call_count == 5:  # estimated minutes
                return _mock_scalar(150)
            elif call_count == 6:  # nodes
                return _mock_scalars([])
            elif call_count == 7:  # mastery
                return _mock_scalar(85.0)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await svc.get_resume("user-1")
        assert result["type"] == "completed"
        assert result["mastery"] == 85.0

    @pytest.mark.asyncio
    async def test_completed_no_path(self):
        from app.services.resume import ResumeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = ResumeService(db)
        goal = _make_goal(status="completed", current_path_id=None)

        db.execute = AsyncMock(return_value=_mock_scalar_result(goal))

        result = await svc.get_resume("user-1")
        assert result["type"] == "completed"
        assert result["path_id"] == ""

    @pytest.mark.asyncio
    async def test_fallback_to_empty_for_unknown_status(self):
        from app.services.resume import ResumeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = ResumeService(db)
        goal = _make_goal(status="unknown_status", current_path_id=None, active_task_id=None)

        db.execute = AsyncMock(return_value=_mock_scalar_result(goal))

        result = await svc.get_resume("user-1")
        assert result["type"] == "empty"


class TestResumeServicePathStats:
    @pytest.mark.asyncio
    async def test_path_stats_no_path(self):
        from app.services.resume import ResumeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = ResumeService(db)
        db.execute = AsyncMock(return_value=_mock_scalar_result(None))

        result = await svc._get_path_stats("path-1", "user-1")
        assert result == {}

    @pytest.mark.asyncio
    async def test_path_stats_no_active_version(self):
        from app.services.resume import ResumeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = ResumeService(db)
        path = MagicMock()
        path.active_version_id = None
        db.execute = AsyncMock(return_value=_mock_scalar_result(path))

        result = await svc._get_path_stats("path-1", "user-1")
        assert result == {}

    @pytest.mark.asyncio
    async def test_path_stats_with_data(self):
        from app.services.resume import ResumeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = ResumeService(db)
        path = MagicMock()
        path.active_version_id = "ver-1"

        node1 = MagicMock()
        node1.id = "n1"
        node1.title = "Node 1"
        prog1 = MagicMock()
        prog1.status = "completed"

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # path
                return _mock_scalar_result(path)
            elif call_count == 2:  # total nodes
                return _mock_scalar(5)
            elif call_count == 3:  # completed
                return _mock_scalar(2)
            elif call_count == 4:  # minutes
                return _mock_scalar(200)
            elif call_count == 5:  # nodes
                return _mock_scalars([node1])
            elif call_count == 6:  # progress for node1
                return _mock_scalar_result(prog1)
            elif call_count == 7:  # mastery
                return _mock_scalar(60.5)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await svc._get_path_stats("path-1", "user-1")
        assert result["total_nodes"] == 5
        assert result["completed_nodes"] == 2
        assert result["progress"] == 40
        assert result["estimated_minutes"] == 200
        assert result["mastery"] == 60.5


class TestResumeServiceStageLabels:
    def test_stage_labels(self):
        from app.services.resume import ResumeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = ResumeService(db)
        assert svc._get_stage_label("clarifying") == "目标澄清"
        assert svc._get_stage_label("diagnosing") == "能力诊断"
        assert svc._get_stage_label("planning") == "路径规划"
        assert svc._get_stage_label("unknown") == "处理中"

    def test_stage_messages(self):
        from app.services.resume import ResumeService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = ResumeService(db)
        assert "澄清" in svc._get_stage_message("clarifying")
        assert "诊断" in svc._get_stage_message("diagnosing")
        assert "梳理" in svc._get_stage_message("planning")
        assert "处理中" in svc._get_stage_message("unknown")
