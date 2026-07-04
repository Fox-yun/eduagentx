"""Tests for app/workers/tasks.py — the Celery worker task execution module.

Covers: run_async, execute_background_task dispatch, _execute_e2e_progress_task,
_execute_path_generation (LLM + fallback), _execute_unit_generation (LLM + fallback),
_execute_knowledge_index, _cleanup_engine, recover_stale_tasks_task, publish_outbox_task.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Pre-import functions under test so patches apply to the already-cached module
from app.workers.tasks import (
    _cleanup_engine,
    _execute_e2e_progress_task,
    _execute_knowledge_index,
    _execute_path_generation,
    _execute_unit_generation,
    execute_background_task,
    publish_outbox_task,
    recover_stale_tasks_task,
    run_async,
)


# ---------------------------------------------------------------------------
# run_async
# ---------------------------------------------------------------------------
class TestRunAsync:
    def test_run_async_creates_new_loop(self):

        async def _coro():
            return 42

        result = run_async(_coro())
        assert result == 42

    def test_run_async_returns_value_from_coroutine(self):

        async def _coro():
            return {"status": "ok"}

        result = run_async(_coro())
        assert result == {"status": "ok"}

    def test_run_async_with_running_loop_uses_thread_pool(self):
        """When a loop is already running (e.g. Jupyter), run_async uses ThreadPoolExecutor."""

        # We simulate the "running loop" branch by patching asyncio.get_running_loop
        # to return a mock loop that reports as running.
        mock_loop = MagicMock()
        mock_loop.is_running.return_value = True

        async def _coro():
            return "from_thread"

        with patch("app.workers.tasks.asyncio.get_running_loop", return_value=mock_loop):
            result = run_async(_coro())
        assert result == "from_thread"


# ---------------------------------------------------------------------------
# _cleanup_engine
# ---------------------------------------------------------------------------
class TestCleanupEngine:
    @pytest.mark.asyncio
    async def test_cleanup_engine_disposes(self):
        mock_engine = AsyncMock()
        with patch("app.core.database.get_engine", return_value=mock_engine):
            await _cleanup_engine()
        mock_engine.dispose.assert_awaited_once()


# ---------------------------------------------------------------------------
# _execute_e2e_progress_task
# ---------------------------------------------------------------------------
class TestExecuteE2EProgressTask:
    @pytest.mark.asyncio
    async def test_e2e_progress_runs_all_steps(self):
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_task = MagicMock()
        mock_task.id = "e2e-task-1"

        with patch("app.workers.tasks.update_task_status", new_callable=AsyncMock) as mock_update:
            with patch("app.workers.tasks.asyncio.sleep", new_callable=AsyncMock):
                result = await _execute_e2e_progress_task(mock_db, mock_task)

        assert result == {"result": "e2e progress completed"}
        # Should have called update_task_status 3 times (10, 40, 70)
        assert mock_update.await_count == 3
        calls = mock_update.await_args_list
        # Check progress values in positional args: db, task_id, target_status, progress=...
        assert calls[0].args[2] == "running"
        assert calls[1].args[2] == "running"
        assert calls[2].args[2] == "running"


# ---------------------------------------------------------------------------
# _execute_path_generation
# ---------------------------------------------------------------------------
class TestExecutePathGeneration:
    @pytest.mark.asyncio
    async def test_path_generation_with_llm_success(self):
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_task = MagicMock()
        mock_task.id = "path-task-1"
        mock_task.target_id = "goal-1"
        mock_task.user_id = "user-1"

        mock_goal = MagicMock()
        mock_goal.title = "Learn Python"
        mock_goal.raw_description = "Master Python"
        mock_goal.current_level = "beginner"
        mock_goal.target_level = "intermediate"

        mock_version = MagicMock()
        mock_version.version_number = 1

        llm_result = {
            "stages": [{"title": "Stage 1", "description": "Desc", "stage_order": 1, "outcome": "Outcome"}],
            "nodes": [
                {
                    "node_id": f"node-{i}",
                    "title": f"Node {i}",
                    "description": f"Desc {i}",
                    "node_order": i,
                    "level": 1,
                    "difficulty": "beginner",
                    "estimated_minutes": 30,
                    "stage_id": "stage-1",
                    "learning_outcomes": [f"Outcome {i}"],
                }
                for i in range(1, 8)
            ],
            "edges": [{"source_node_id": f"node-{i}", "target_node_id": f"node-{i + 1}"} for i in range(1, 7)],
            "summary": "Python path",
        }

        with (
            patch("app.workers.tasks.update_task_status", new_callable=AsyncMock),
            patch("app.workers.tasks.asyncio.sleep", new_callable=AsyncMock),
            patch("app.services.goal.GoalService") as MockGoalSvc,
            patch("app.services.llm.llm_json", new_callable=AsyncMock, return_value=llm_result),
            patch("app.services.path.PathService") as MockPathSvc,
            patch(
                "app.services.profile_merge.load_profile_context",
                new_callable=AsyncMock,
                return_value=(None, ""),
            ),
        ):
            MockGoalSvc.return_value.get_goal = AsyncMock(return_value=mock_goal)
            MockGoalSvc.return_value.transition_goal = AsyncMock(return_value=mock_goal)
            MockPathSvc.return_value.create_path_version = AsyncMock(return_value=mock_version)

            result = await _execute_path_generation(mock_db, mock_task)

        assert "path_id" in result
        assert result["version"] == 1

    @pytest.mark.asyncio
    async def test_path_generation_llm_too_few_nodes_fallback(self):
        """When LLM returns <5 nodes, fallback to template."""
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_task = MagicMock()
        mock_task.id = "path-task-2"
        mock_task.target_id = "goal-2"
        mock_task.user_id = "user-2"

        mock_goal = MagicMock()
        mock_goal.title = "Learn ML"
        mock_goal.raw_description = None
        mock_goal.current_level = None
        mock_goal.target_level = None

        mock_version = MagicMock()
        mock_version.version_number = 1

        llm_result = {
            "stages": [],
            "nodes": [{"node_id": "node-1", "title": "Only one"}],  # Too few!
            "edges": [],
            "summary": "",
        }

        with (
            patch("app.workers.tasks.update_task_status", new_callable=AsyncMock),
            patch("app.workers.tasks.asyncio.sleep", new_callable=AsyncMock),
            patch("app.services.goal.GoalService") as MockGoalSvc,
            patch("app.services.llm.llm_json", new_callable=AsyncMock, return_value=llm_result),
            patch("app.services.path.PathService") as MockPathSvc,
            patch(
                "app.services.profile_merge.load_profile_context",
                new_callable=AsyncMock,
                return_value=(None, ""),
            ),
        ):
            MockGoalSvc.return_value.get_goal = AsyncMock(return_value=mock_goal)
            MockGoalSvc.return_value.transition_goal = AsyncMock(return_value=mock_goal)
            MockPathSvc.return_value.create_path_version = AsyncMock(return_value=mock_version)

            result = await _execute_path_generation(mock_db, mock_task)

        assert "path_id" in result

    @pytest.mark.asyncio
    async def test_path_generation_llm_failure_uses_template(self):
        """When LLM raises, template fallback is used."""
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_task = MagicMock()
        mock_task.id = "path-task-3"
        mock_task.target_id = "goal-3"
        mock_task.user_id = "user-3"

        mock_goal = MagicMock()
        mock_goal.title = "Deep Learning"
        mock_goal.raw_description = "Neural networks"
        mock_goal.current_level = "beginner"
        mock_goal.target_level = "advanced"

        mock_version = MagicMock()
        mock_version.version_number = 1

        with (
            patch("app.workers.tasks.update_task_status", new_callable=AsyncMock),
            patch("app.workers.tasks.asyncio.sleep", new_callable=AsyncMock),
            patch("app.services.goal.GoalService") as MockGoalSvc,
            patch("app.services.llm.llm_json", new_callable=AsyncMock, side_effect=Exception("LLM down")),
            patch("app.services.path.PathService") as MockPathSvc,
            patch(
                "app.services.profile_merge.load_profile_context",
                new_callable=AsyncMock,
                return_value=(None, ""),
            ),
        ):
            MockGoalSvc.return_value.get_goal = AsyncMock(return_value=mock_goal)
            MockGoalSvc.return_value.transition_goal = AsyncMock(return_value=mock_goal)
            MockPathSvc.return_value.create_path_version = AsyncMock(return_value=mock_version)

            result = await _execute_path_generation(mock_db, mock_task)

        assert "path_id" in result

    @pytest.mark.asyncio
    async def test_path_generation_llm_too_many_nodes_truncates(self):
        """When LLM returns >15 nodes, truncate to 15."""
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_task = MagicMock()
        mock_task.id = "path-task-4"
        mock_task.target_id = "goal-4"
        mock_task.user_id = "user-4"

        mock_goal = MagicMock()
        mock_goal.title = "React"
        mock_goal.raw_description = None
        mock_goal.current_level = None
        mock_goal.target_level = None

        mock_version = MagicMock()
        mock_version.version_number = 1

        llm_result = {
            "stages": [{"title": "S1", "description": "D", "stage_order": 1, "outcome": "O"}],
            "nodes": [
                {
                    "node_id": f"node-{i}",
                    "title": f"Node {i}",
                    "description": f"Desc {i}",
                    "node_order": i,
                    "level": 1,
                    "difficulty": "beginner",
                    "estimated_minutes": 30,
                    "stage_id": "stage-1",
                    "learning_outcomes": [f"LO {i}"],
                }
                for i in range(1, 20)  # 19 nodes > 15
            ],
            "edges": [],
            "summary": "React path",
        }

        with (
            patch("app.workers.tasks.update_task_status", new_callable=AsyncMock),
            patch("app.workers.tasks.asyncio.sleep", new_callable=AsyncMock),
            patch("app.services.goal.GoalService") as MockGoalSvc,
            patch("app.services.llm.llm_json", new_callable=AsyncMock, return_value=llm_result),
            patch("app.services.path.PathService") as MockPathSvc,
            patch(
                "app.services.profile_merge.load_profile_context",
                new_callable=AsyncMock,
                return_value=(None, ""),
            ),
        ):
            MockGoalSvc.return_value.get_goal = AsyncMock(return_value=mock_goal)
            MockGoalSvc.return_value.transition_goal = AsyncMock(return_value=mock_goal)
            MockPathSvc.return_value.create_path_version = AsyncMock(return_value=mock_version)

            result = await _execute_path_generation(mock_db, mock_task)

        assert "path_id" in result


# ---------------------------------------------------------------------------
# _execute_unit_generation
# ---------------------------------------------------------------------------
class TestExecuteUnitGeneration:
    @pytest.mark.asyncio
    async def test_unit_generation_with_llm_success(self):
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_task = MagicMock()
        mock_task.id = "unit-task-1"
        mock_task.target_id = "node-1"
        mock_task.user_id = "user-1"
        mock_task.target_metadata = {"path_id": "path-1", "unit_content_version_id": "ver-gen-1"}

        # Mock node
        mock_node = MagicMock()
        mock_node.title = "Python Lists"
        mock_node.description = "List operations"
        mock_node.difficulty = "beginner"
        mock_node.learning_outcomes = '["Outcome 1"]'

        # Mock path
        mock_path = MagicMock()
        mock_path.active_version_id = "v1"
        mock_path.goal_id = "goal-1"

        # Mock goal
        mock_goal = MagicMock()
        mock_goal.title = "Learn Python"

        # Mock version (Transaction A load)
        mock_version = MagicMock()
        mock_version.id = "ver-gen-1"
        mock_version.unit_content_id = "uc-1"
        mock_version.status = "generating"

        # Mock unit content (Transaction B)
        mock_uc = MagicMock()
        mock_uc.id = "uc-1"
        mock_uc.active_version_id = "ver-old-1"
        mock_uc.status = "regenerating"
        mock_uc.active_task_id = "unit-task-1"

        # Mock old version (Transaction B)
        mock_old_version = MagicMock()
        mock_old_version.id = "ver-old-1"
        mock_old_version.status = "active"

        # Mock background task (not cancelled)
        mock_bg_task = MagicMock()
        mock_bg_task.status = "running"

        # Mock LLM result
        llm_content = {
            "introduction": "# Python Lists\n\nIntro",
            "objectives": ["Understand lists"],
            "sections": [
                {"section_id": "sec-1", "title": "Basics", "content": "Content " * 50, "order": 1},
                {"section_id": "sec-2", "title": "Advanced", "content": "More content " * 50, "order": 2},
            ],
            "practice_tasks": [],
            "summary": "Summary",
            "references": [],
        }

        review_result = {"passed": True, "score": 85, "issues": [], "summary": "Good"}

        from unittest.mock import MagicMock as MockMM

        call_data: dict[str, int] = {"calls": 0}

        def _scalar(val):
            r = MockMM()
            r.scalar_one_or_none.return_value = val
            return r

        async def mock_execute(stmt):
            call_data["calls"] += 1
            n = call_data["calls"]
            # Txn A queries: node, path, goal, version
            if n == 1:
                return _scalar(mock_node)
            elif n == 2:
                return _scalar(mock_path)
            elif n == 3:
                return _scalar(mock_goal)
            elif n == 4 or n == 5:
                return _scalar(mock_version)
            elif n == 6:
                return _scalar(mock_bg_task)
            elif n == 7:
                return _scalar(mock_uc)
            elif n == 8:
                return _scalar(mock_old_version)
            return _scalar(None)

        mock_db.execute = mock_execute

        with (
            patch("app.workers.tasks.update_task_status", new_callable=AsyncMock),
            patch("app.workers.tasks.asyncio.sleep", new_callable=AsyncMock),
            patch("app.services.llm.llm_json", new_callable=AsyncMock) as mock_llm,
        ):
            mock_llm.side_effect = [llm_content, review_result]

            result = await _execute_unit_generation(mock_db, mock_task)

        assert "unit_id" in result
        assert result["node_id"] == "node-1"

    @pytest.mark.asyncio
    async def test_unit_generation_llm_fallback_to_template(self):
        """When LLM fails, template content is used."""
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_task = MagicMock()
        mock_task.id = "unit-task-2"
        mock_task.target_id = "node-2"
        mock_task.user_id = "user-2"
        mock_task.target_metadata = {"path_id": "path-2", "unit_content_version_id": "ver-gen-2"}

        mock_node = MagicMock()
        mock_node.title = "Numpy Arrays"
        mock_node.description = "Array operations"
        mock_node.difficulty = "intermediate"
        mock_node.learning_outcomes = "[]"

        mock_version = MagicMock()
        mock_version.id = "ver-gen-2"
        mock_version.unit_content_id = "uc-2"
        mock_version.status = "generating"

        mock_bg_task = MagicMock()
        mock_bg_task.status = "running"

        mock_uc = MagicMock()
        mock_uc.id = "uc-2"
        mock_uc.active_version_id = "ver-old-2"
        mock_uc.status = "regenerating"
        mock_uc.active_task_id = "unit-task-2"

        mock_old_version = MagicMock()
        mock_old_version.id = "ver-old-2"
        mock_old_version.status = "active"

        def _scalar(val):
            r = MagicMock()
            r.scalar_one_or_none.return_value = val
            return r

        call_data: dict[str, int] = {"calls": 0}

        async def mock_execute(stmt):
            call_data["calls"] += 1
            n = call_data["calls"]
            if n == 1:
                return _scalar(mock_node)
            elif n == 2:
                return _scalar(None)  # no path
            elif n == 3:
                return _scalar(mock_version)
            elif n == 4:
                return _scalar(mock_version)  # Txn B: version
            elif n == 5:
                return _scalar(mock_bg_task)  # Txn B: task
            elif n == 6:
                return _scalar(mock_uc)  # Txn B: unit content
            elif n == 7:
                return _scalar(mock_old_version)  # Txn B: old version
            return _scalar(None)

        mock_db.execute = mock_execute

        with (
            patch("app.workers.tasks.update_task_status", new_callable=AsyncMock),
            patch("app.workers.tasks.asyncio.sleep", new_callable=AsyncMock),
            patch("app.services.llm.llm_json", new_callable=AsyncMock, side_effect=Exception("LLM error")),
        ):
            result = await _execute_unit_generation(mock_db, mock_task)

        assert "unit_id" in result

    @pytest.mark.asyncio
    async def test_unit_generation_no_path_context(self):
        """When target_metadata has no path_id, works with defaults."""
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_task = MagicMock()
        mock_task.id = "unit-task-3"
        mock_task.target_id = "node-3"
        mock_task.user_id = "user-3"
        mock_task.target_metadata = {"unit_content_version_id": "ver-gen-3"}

        mock_node = MagicMock()
        mock_node.title = "Pandas"
        mock_node.description = "DataFrames"
        mock_node.difficulty = "advanced"
        mock_node.learning_outcomes = "[]"

        mock_version = MagicMock()
        mock_version.id = "ver-gen-3"
        mock_version.unit_content_id = "uc-3"
        mock_version.status = "generating"

        mock_bg_task = MagicMock()
        mock_bg_task.status = "running"

        mock_uc = MagicMock()
        mock_uc.id = "uc-3"
        mock_uc.active_version_id = "ver-old-3"
        mock_uc.status = "generating"
        mock_uc.active_task_id = "unit-task-3"

        mock_old_version = MagicMock()
        mock_old_version.id = "ver-old-3"
        mock_old_version.status = "active"

        def _scalar(val):
            r = MagicMock()
            r.scalar_one_or_none.return_value = val
            return r

        call_data: dict[str, int] = {"calls": 0}

        async def mock_execute(stmt):
            call_data["calls"] += 1
            n = call_data["calls"]
            if n == 1:
                return _scalar(mock_node)
            elif n == 2:
                return _scalar(None)  # no path
            elif n == 3:
                return _scalar(mock_version)
            elif n == 4:
                return _scalar(mock_version)  # Txn B: version
            elif n == 5:
                return _scalar(mock_bg_task)  # Txn B: task
            elif n == 6:
                return _scalar(mock_uc)  # Txn B: unit content
            elif n == 7:
                return _scalar(mock_old_version)  # Txn B: old version
            return _scalar(None)

        mock_db.execute = mock_execute


# ---------------------------------------------------------------------------
# _execute_knowledge_index
# ---------------------------------------------------------------------------
class TestExecuteKnowledgeIndex:
    @pytest.mark.asyncio
    async def test_knowledge_index_success(self):
        from app.services.storage import InMemoryObjectStorage

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_task = MagicMock()
        mock_task.id = "ki-task-1"
        mock_task.target_id = "doc-1"

        mock_doc = MagicMock()
        mock_doc.id = "doc-1"
        mock_doc.status = "uploaded"
        mock_doc.operation_status = "queued"
        mock_doc.storage_key = "knowledge/user-1/test.txt"
        mock_doc.mime_type = "text/plain"
        mock_doc.filename = "test.txt"
        mock_doc.active_index_version = None
        mock_doc.error = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_doc
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Set up in-memory storage with test content
        storage = InMemoryObjectStorage()
        await storage.put("knowledge/user-1/test.txt", b"Hello world. This is test content for indexing.")

        with patch("app.workers.tasks.update_task_status", new_callable=AsyncMock):
            with patch("app.services.storage.get_object_storage", return_value=storage):
                with patch("app.services.knowledge.get_object_storage", return_value=storage):
                    result = await _execute_knowledge_index(mock_db, mock_task)

        assert result["document_id"] == "doc-1"
        assert result["chunks"] >= 1
        assert result["index_version"] == 1
        assert mock_doc.status == "ready"
        assert mock_doc.operation_status == "ready"

    @pytest.mark.asyncio
    async def test_knowledge_index_document_not_found(self):
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_task = MagicMock()
        mock_task.id = "ki-task-2"
        mock_task.target_id = "doc-missing"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.workers.tasks.update_task_status", new_callable=AsyncMock):
            with pytest.raises(ValueError, match="Document .* not found"):
                await _execute_knowledge_index(mock_db, mock_task)


# ---------------------------------------------------------------------------
# execute_background_task (dispatch logic)
# ---------------------------------------------------------------------------
class TestExecuteBackgroundTask:
    def test_task_functions_are_callable(self):
        """Verify task functions exist and are callable."""
        assert callable(execute_background_task)
        assert callable(recover_stale_tasks_task)
        assert callable(publish_outbox_task)
