"""Comprehensive unit tests for PathService."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.errors import ApiError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_path(**overrides):
    """Create a mock LearningPath."""
    p = MagicMock()
    p.id = overrides.get("id", "path-1")
    p.user_id = overrides.get("user_id", "user-1")
    p.goal_id = overrides.get("goal_id", "goal-1")
    p.active_version_id = overrides.get("active_version_id")
    p.status = overrides.get("status", "draft")
    p.created_at = overrides.get("created_at", datetime.now(UTC))
    p.updated_at = overrides.get("updated_at", datetime.now(UTC))
    return p


def _make_version(**overrides):
    """Create a mock LearningPathVersion."""
    v = MagicMock()
    v.id = overrides.get("id", "ver-1")
    v.path_id = overrides.get("path_id", "path-1")
    v.version_number = overrides.get("version_number", 1)
    v.status = overrides.get("status", "draft")
    v.summary = overrides.get("summary", "Test summary")
    v.estimated_total_minutes = overrides.get("estimated_total_minutes", 120)
    v.activated_at = overrides.get("activated_at")
    return v


def _make_node(**overrides):
    """Create a mock LearningNode."""
    n = MagicMock()
    n.id = overrides.get("id", "node-1")
    n.version_id = overrides.get("version_id", "ver-1")
    n.stage_id = overrides.get("stage_id")
    n.title = overrides.get("title", "Test Node")
    n.description = overrides.get("description", "desc")
    n.node_order = overrides.get("node_order", 1)
    n.level = overrides.get("level", 1)
    n.difficulty = overrides.get("difficulty", "beginner")
    n.estimated_minutes = overrides.get("estimated_minutes", 30)
    n.status = overrides.get("status", "locked")
    n.mastery = overrides.get("mastery", 0.0)
    n.content_status = overrides.get("content_status", "not_generated")
    n.learning_outcomes = overrides.get("learning_outcomes", '["outcome1"]')
    n.assessment_strategy = overrides.get("assessment_strategy")
    n.generation_reason = overrides.get("generation_reason")
    return n


def _make_edge(**overrides):
    """Create a mock LearningEdge."""
    e = MagicMock()
    e.id = overrides.get("id", "edge-1")
    e.version_id = overrides.get("version_id", "ver-1")
    e.source_node_id = overrides.get("source_node_id", "node-1")
    e.target_node_id = overrides.get("target_node_id", "node-2")
    return e


def _make_stage(**overrides):
    """Create a mock LearningStage."""
    s = MagicMock()
    s.id = overrides.get("id", "stage-1")
    s.version_id = overrides.get("version_id", "ver-1")
    s.title = overrides.get("title", "Stage 1")
    s.description = overrides.get("description", "desc")
    s.stage_order = overrides.get("stage_order", 1)
    s.outcome = overrides.get("outcome", "outcome")
    return s


def _mock_scalar_result(value):
    """Create a mock result with scalar_one_or_none returning value."""
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _mock_scalars(items):
    """Create a mock result with scalars().all() returning items."""
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


def _mock_scalar(value):
    """Create a mock result with scalar() returning value."""
    r = MagicMock()
    r.scalar.return_value = value
    return r


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPathServiceGetPath:
    @pytest.mark.asyncio
    async def test_get_path_found(self):
        from app.services.path import PathService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = PathService(db)
        path = _make_path()
        db.execute = AsyncMock(return_value=_mock_scalar_result(path))

        result = await svc.get_path("path-1", "user-1")
        assert result is path

    @pytest.mark.asyncio
    async def test_get_path_not_found(self):
        from app.services.path import PathService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = PathService(db)
        db.execute = AsyncMock(return_value=_mock_scalar_result(None))

        with pytest.raises(ApiError) as exc_info:
            await svc.get_path("nonexistent", "user-1")
        assert exc_info.value.code == "PATH_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_get_path_wrong_user(self):
        from app.services.path import PathService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = PathService(db)
        db.execute = AsyncMock(return_value=_mock_scalar_result(None))

        with pytest.raises(ApiError):
            await svc.get_path("path-1", "wrong-user")


class TestPathServiceGetPathWithDetails:
    @pytest.mark.asyncio
    async def test_returns_formatted_path_with_version(self):
        from app.services.path import PathService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = PathService(db)
        path = _make_path(active_version_id="ver-1")
        version = _make_version()
        stages = [_make_stage()]
        nodes = [_make_node(stage_id="stage-1")]
        edges = [_make_edge()]

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # get_path
                return _mock_scalar_result(path)
            elif call_count == 2:  # version query
                return _mock_scalar_result(version)
            elif call_count == 3:  # stages
                return _mock_scalars(stages)
            elif call_count == 4:  # nodes
                return _mock_scalars(nodes)
            elif call_count == 5:  # edges
                return _mock_scalars(edges)
            elif call_count == 6:  # per-user progress
                return _mock_scalars([])
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await svc.get_path_with_details("path-1", "user-1")
        assert result["path_id"] == "path-1"
        assert result["status"] == "draft"
        assert len(result["nodes"]) == 1
        assert len(result["stages"]) == 1
        assert len(result["edges"]) == 1

    @pytest.mark.asyncio
    async def test_returns_path_with_no_version(self):
        from app.services.path import PathService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = PathService(db)
        path = _make_path(active_version_id=None)

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(path)
            elif call_count == 2:
                return _mock_scalar_result(None)  # no version
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await svc.get_path_with_details("path-1", "user-1")
        assert result["nodes"] == []
        assert result["stages"] == []
        assert result["edges"] == []


class TestPathServiceCreatePathVersion:
    @pytest.mark.asyncio
    async def test_creates_version_with_dag(self):
        from app.services.path import PathService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = PathService(db)
        path = _make_path()

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # get_path
                return _mock_scalar_result(path)
            elif call_count == 2:  # get next version number
                return _mock_scalar(None)  # no previous version
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with patch("app.services.path.validate_dag"):
            version = await svc.create_path_version(
                path_id="path-1",
                user_id="user-1",
                stages=[{"title": "Stage 1", "stage_order": 1, "stage_id": "s1"}],
                nodes=[
                    {"title": "Node 1", "node_id": "n1", "stage_id": "s1", "estimated_minutes": 30, "node_order": 1},
                    {"title": "Node 2", "node_id": "n2", "stage_id": "s1", "estimated_minutes": 40, "node_order": 2},
                ],
                edges=[{"source_node_id": "n1", "target_node_id": "n2"}],
                summary="Test summary",
            )
            assert version is not None
            assert db.add.call_count >= 3  # version + 2 stages? + nodes + edges
            assert db.flush.call_count >= 2
            db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_creates_version_no_previous(self):
        from app.services.path import PathService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = PathService(db)
        path = _make_path()

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(path)
            elif call_count == 2:
                return _mock_scalar(None)  # no previous version
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with patch("app.services.path.validate_dag"):
            version = await svc.create_path_version(
                path_id="path-1",
                user_id="user-1",
                stages=[],
                nodes=[{"title": "Node 1", "node_id": "n1", "estimated_minutes": 30}],
                edges=[],
            )
            assert version.version_number == 1

    @pytest.mark.asyncio
    async def test_creates_version_with_previous(self):
        from app.services.path import PathService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = PathService(db)
        path = _make_path()

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(path)
            elif call_count == 2:
                return _mock_scalar(3)  # previous version 3
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with patch("app.services.path.validate_dag"):
            version = await svc.create_path_version(
                path_id="path-1",
                user_id="user-1",
                stages=[],
                nodes=[{"title": "Node 1", "node_id": "n1", "estimated_minutes": 30}],
                edges=[],
            )
            assert version.version_number == 4

    @pytest.mark.asyncio
    async def test_dag_validation_called(self):
        from app.services.path import PathService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = PathService(db)
        path = _make_path()

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(path)
            elif call_count == 2:
                return _mock_scalar(None)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with patch("app.services.path.validate_dag") as mock_dag:
            await svc.create_path_version(
                path_id="path-1",
                user_id="user-1",
                stages=[],
                nodes=[{"title": "N1", "node_id": "n1", "estimated_minutes": 30}],
                edges=[],
            )
            mock_dag.assert_called_once()

    @pytest.mark.asyncio
    async def test_path_not_found_raises(self):
        from app.services.path import PathService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = PathService(db)
        db.execute = AsyncMock(return_value=_mock_scalar_result(None))

        with pytest.raises(ApiError) as exc_info:
            await svc.create_path_version("bad-path", "user-1", [], [], [])
        assert exc_info.value.code == "PATH_NOT_FOUND"


class TestPathServiceActivateVersion:
    @pytest.mark.asyncio
    async def test_activate_latest_version_delegates_to_atomic_activation(self):
        from app.services.path import PathService

        db = AsyncMock()
        version = _make_version(id="ver-2", version_number=2, status="in_review")
        path = _make_path()
        db.execute = AsyncMock(return_value=_mock_scalar_result(version))
        svc = PathService(db)
        svc.activate_version = AsyncMock(return_value=path)

        result_path, version_id = await svc.activate_latest_version("path-1", "user-1")

        assert result_path is path
        assert version_id == "ver-2"
        svc.activate_version.assert_awaited_once_with("path-1", "user-1", "ver-2")

    @pytest.mark.asyncio
    async def test_activate_latest_version_requires_draft_or_review(self):
        from app.services.path import PathService

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_mock_scalar_result(None))
        svc = PathService(db)

        with pytest.raises(ApiError) as exc_info:
            await svc.activate_latest_version("path-1", "user-1")

        assert exc_info.value.code == "NO_ACTIVATABLE_VERSION"
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_activate_version_success(self):
        from app.services.path import PathService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = PathService(db)
        path = _make_path(active_version_id=None, status="draft")
        version = _make_version(status="draft")

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # FOR UPDATE path
                return _mock_scalar_result(path)
            elif call_count == 2:  # get version
                return _mock_scalar_result(version)
            elif call_count == 3 or call_count == 4:  # _initialize_node_statuses: get nodes
                return _mock_scalars([])
            elif call_count == 5:  # update goal
                return MagicMock()
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await svc.activate_version("path-1", "user-1", "ver-1")
        assert result is path
        assert version.status == "active"
        assert version.activated_at is not None

    @pytest.mark.asyncio
    async def test_activate_version_not_found(self):
        from app.services.path import PathService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = PathService(db)
        path = _make_path()

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(path)
            elif call_count == 2:
                return _mock_scalar_result(None)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with pytest.raises(ApiError) as exc_info:
            await svc.activate_version("path-1", "user-1", "bad-ver")
        assert exc_info.value.code == "VERSION_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_activate_version_invalid_status(self):
        from app.services.path import PathService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = PathService(db)
        path = _make_path()
        version = _make_version(status="active")  # already active

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(path)
            elif call_count == 2:
                return _mock_scalar_result(version)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with pytest.raises(ApiError) as exc_info:
            await svc.activate_version("path-1", "user-1", "ver-1")
        assert exc_info.value.code == "INVALID_STATUS"

    @pytest.mark.asyncio
    async def test_activate_version_supersedes_old_active(self):
        """New activation supersedes the old active version."""
        from app.services.path import PathService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = PathService(db)
        path = _make_path(active_version_id="old-ver")
        old_version = _make_version(id="old-ver", status="active")
        version = _make_version(status="draft")

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # FOR UPDATE path
                return _mock_scalar_result(path)
            elif call_count == 2:  # get target version
                return _mock_scalar_result(version)
            elif call_count == 3:  # get old active version
                return _mock_scalar_result(old_version)
            elif call_count == 4 or call_count == 5:  # _initialize_node_statuses: get nodes
                return _mock_scalars([])
            elif call_count == 6:  # update goal
                return MagicMock()
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await svc.activate_version("path-1", "user-1", "ver-1")
        assert result is path
        assert old_version.status == "superseded"
        assert version.status == "active"


class TestPathServiceInitializeNodeStatuses:
    @pytest.mark.asyncio
    async def test_root_nodes_become_available(self):
        from app.services.path import PathService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = PathService(db)

        node1 = _make_node(id="node-1")
        node2 = _make_node(id="node-2")
        edge = _make_edge(source_node_id="node-1", target_node_id="node-2")

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalars([node1, node2])
            elif call_count == 2:
                return _mock_scalars([edge])
            return _mock_scalars([])

        db.execute = AsyncMock(side_effect=execute_side_effect)

        await svc._initialize_node_statuses("ver-1")
        assert node1.status == "available"
        assert node2.status == "locked"

    @pytest.mark.asyncio
    async def test_no_edges_all_roots(self):
        from app.services.path import PathService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = PathService(db)

        node1 = _make_node(id="node-1")
        node2 = _make_node(id="node-2")

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalars([node1, node2])
            elif call_count == 2:
                return _mock_scalars([])
            return _mock_scalars([])

        db.execute = AsyncMock(side_effect=execute_side_effect)

        await svc._initialize_node_statuses("ver-1")
        assert node1.status == "available"
        assert node2.status == "available"


class TestPathServiceRevisionRequest:
    @pytest.mark.asyncio
    async def test_create_revision_request(self):
        from app.services.path import PathService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = PathService(db)
        path = _make_path(active_version_id="ver-1")

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(path)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        revision_req, task = await svc.create_revision_request("path-1", "user-1", "Please revise")
        assert revision_req is not None
        assert revision_req.revision_request == "Please revise"
        db.add.assert_called()

    @pytest.mark.asyncio
    async def test_create_revision_request_uses_latest_draft_before_first_activation(self):
        from app.services.path import PathService

        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        svc = PathService(db)
        path = _make_path(active_version_id=None, status="draft")
        draft = _make_version(id="draft-ver-2", version_number=2, status="draft")

        db.execute = AsyncMock(
            side_effect=[
                _mock_scalar_result(path),
                _mock_scalar_result(draft),
                _mock_scalar_result(None),
            ]
        )
        task = MagicMock(id="revision-task-1")
        with patch(
            "app.services.task.TaskService.enqueue_task",
            new_callable=AsyncMock,
            return_value=task,
        ) as enqueue:
            revision_req, returned_task = await svc.create_revision_request(
                "path-1", "user-1", "增加更多实践"
            )

        assert revision_req.source_version_id == "draft-ver-2"
        assert revision_req.task_id == "revision-task-1"
        assert returned_task is task
        assert enqueue.await_args.kwargs["target_metadata"] == {
            "path_id": "path-1",
            "source_version_id": "draft-ver-2",
        }

    @pytest.mark.asyncio
    async def test_create_revision_request_rejects_path_without_any_source_version(self):
        from app.services.path import PathService

        db = AsyncMock()
        svc = PathService(db)
        path = _make_path(active_version_id=None, status="draft")
        db.execute = AsyncMock(
            side_effect=[_mock_scalar_result(path), _mock_scalar_result(None)]
        )

        with pytest.raises(ApiError) as exc_info:
            await svc.create_revision_request("path-1", "user-1", "增加更多实践")

        assert exc_info.value.code == "NO_REVISION_SOURCE"


class TestPathServiceListVersions:
    @pytest.mark.asyncio
    async def test_list_versions(self):
        from app.services.path import PathService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = PathService(db)
        path = _make_path()
        versions = [_make_version(version_number=i) for i in range(1, 4)]

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(path)
            elif call_count == 2:
                return _mock_scalars(versions)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await svc.list_versions("path-1", "user-1")
        assert len(result) == 3


class TestPathServiceFormatPath:
    @pytest.mark.asyncio
    async def test_format_path_overlays_per_user_progress(self):
        from app.services.path import PathService

        db = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar.return_value = "Python path"
        db.execute.return_value = mock_res
        svc = PathService(db)
        path = _make_path()
        version = _make_version()
        completed_node = _make_node(id="node-1", status="available", mastery=0.0)
        next_node = _make_node(id="node-2", status="locked", mastery=0.0)
        completed_progress = MagicMock(node_id="node-1", status="completed", mastery=92.0)
        available_progress = MagicMock(node_id="node-2", status="available", mastery=0.0)

        result = await svc._format_path(
            path,
            version,
            [],
            [completed_node, next_node],
            [],
            {
                "node-1": completed_progress,
                "node-2": available_progress,
            },
        )

        assert result["nodes"][0]["status"] == "completed"
        assert result["nodes"][0]["mastery"] == 92.0
        assert result["nodes"][1]["status"] == "available"
        assert result["current_node_id"] == "node-2"

    @pytest.mark.asyncio
    async def test_format_path_with_version(self):
        from app.services.path import PathService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        mock_res = MagicMock()
        mock_res.scalar.return_value = "Python 编程基础"
        db.execute.return_value = mock_res
        svc = PathService(db)
        path = _make_path()
        version = _make_version()
        node = _make_node(stage_id="stage-1")
        edge = _make_edge(source_node_id="node-0", target_node_id="node-1")
        stage = _make_stage(id="stage-1")

        result = await svc._format_path(path, version, [stage], [node], [edge])
        assert result["path_id"] == "path-1"
        assert result["version"] == 1
        assert len(result["nodes"]) == 1
        assert len(result["stages"]) == 1
        assert result["stages"][0]["node_ids"] == ["node-1"]

    @pytest.mark.asyncio
    async def test_format_path_no_version(self):
        from app.services.path import PathService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        mock_res = MagicMock()
        mock_res.scalar.return_value = ""
        db.execute.return_value = mock_res
        svc = PathService(db)
        path = _make_path()

        result = await svc._format_path(path, None, [], [], [])
        assert result["title"] == ""
        assert result["total_estimated_minutes"] == 0
        assert result["nodes"] == []
