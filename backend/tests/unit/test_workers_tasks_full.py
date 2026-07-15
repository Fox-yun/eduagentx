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
    _build_fallback_content,
    _build_fallback_lecture,
    _cleanup_engine,
    _execute_e2e_progress_task,
    _execute_knowledge_index,
    _execute_lecture_generation,
    _execute_path_generation,
    _execute_unit_generation,
    _extract_topic,
    _normalize_learning_material,
    _normalize_lecture_material,
    execute_background_task,
    publish_outbox_task,
    recover_stale_tasks_task,
    run_async,
)


class TestLearningContentFallbacks:
    def test_extract_topic_removes_direct_learning_verb(self):
        assert _extract_topic("学习 Python 编程基础和算法") == "Python 编程基础和算法"

    def test_python_basics_fallback_is_runnable_and_specific(self):
        content = _build_fallback_content(
            "Python 环境配置与基本语法",
            "安装解释器并学习变量和控制台交互。",
            "beginner",
            ["运行 Python 脚本", "使用 print 和 input"],
        )

        combined = "\n".join(section["content"] for section in content["sections"])
        assert "python --version" in combined
        assert "input(" in combined
        assert "type(" in combined
        assert "process()" not in combined
        assert content["practice_tasks"][2]["title"] == "制作个人信息卡"
        assert all(section["concepts"] for section in content["sections"])
        assert all(section["checkpoints"] for section in content["sections"])
        assert content["project"]["deliverables"]

    def test_lecture_fallback_preserves_source_without_repeated_boilerplate(self):
        source = {
            "introduction": "# Python 基础\n\n直接开始实践。",
            "objectives": ["运行脚本"],
            "sections": [
                {
                    "title": "首次运行",
                    "content": "执行 `python hello.py`。",
                    "order": 1,
                }
            ],
            "summary": "已完成首次运行。",
        }

        lecture = _build_fallback_lecture("Python 基础", "beginner", source)

        assert lecture["introduction"] == source["introduction"]
        assert lecture["sections"][0]["title"] == "首次运行"
        assert lecture["sections"][0]["content"] == "执行 `python hello.py`。"
        assert lecture["key_takeaways"] == ["运行脚本"]
        assert "深度解析" not in str(lecture)
        assert "process()" not in str(lecture)
        assert lecture["sections"][0]["source_section_id"] == "sec-1"

    def test_python_overview_fallback_has_real_history_examples_and_boundaries(self):
        content = _build_fallback_content(
            "Python 编程概述与发展背景",
            "了解 Python 的定义、应用场景和发展历史",
            "beginner",
            ["理解 Python 的基本定义", "了解典型应用场景"],
        )

        combined = "\n".join(section["content"] for section in content["sections"])
        assert "1991" in combined
        assert "Python 虚拟机" in combined
        assert "FastAPI" in combined
        assert "process()" not in combined
        assert "内部机制和数据流动方式" not in combined
        assert content["completion_criteria"]
        assert content["project"]["deliverables"]

    @pytest.mark.parametrize(
        ("title", "expected"),
        [
            ("Python 的核心概念与术语", "summarize"),
            ("Python 的基本操作与工具", "sys.executable"),
            ("Python 的常见模式与最佳实践", "@dataclass"),
            ("Python 的进阶技巧与性能优化", "timeit"),
            ("Python 的错误处理与调试", "parse_age"),
            ("Python 的项目实战应用", "count_lines"),
            ("Python 的扩展与生态", "importlib.metadata"),
            ("Python 总结与持续学习路径", "next_topic"),
            ("Python 算法与数据结构", "binary_search"),
        ],
    )
    def test_python_topic_fallbacks_are_distinct_and_runnable(self, title, expected):
        content = _build_fallback_content(
            title,
            f"学习{title}中的具体方法",
            "intermediate",
            [f"掌握{title}"],
        )

        combined = "\n".join(section["content"] for section in content["sections"])
        assert expected in combined
        assert "process()" not in combined
        assert "内部机制和数据流动方式" not in combined
        assert len(content["sections"]) == 4
        assert all(section["mind_map_nodes"] for section in content["sections"])

    def test_quality_gate_flags_generic_shallow_material(self):
        material, quality = _normalize_learning_material(
            {
                "sections": [
                    {"title": "概念介绍", "content": "内部机制和数据流动方式，有广泛的应用场景。"}
                ]
            },
            node_title="Python 基础",
            node_difficulty="beginner",
            objectives=["运行脚本"],
        )

        assert quality["passed"] is False
        assert quality["generic_phrase_hits"] >= 1
        assert material["sections"][0]["section_id"] == "sec-1"
        assert material["sections"][0]["checkpoints"]

    def test_lecture_sections_keep_canonical_source_links(self):
        source = {
            "introduction": "开始学习",
            "objectives": ["掌握变量"],
            "sections": [
                {"section_id": "variables", "title": "变量", "content": "变量内容"}
            ],
        }
        lecture, quality = _normalize_lecture_material(
            {
                "introduction": "讲义导入",
                "sections": [
                    {"section_id": "lec-1", "title": "变量详解", "content": "详细内容", "order": 1}
                ],
                "key_takeaways": ["掌握变量"],
                "common_mistakes": [],
                "summary": "完成",
            },
            source=source,
        )

        assert lecture["sections"][0]["source_section_id"] == "variables"
        assert quality["section_count"] == 1


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
        mock_task.agent_trace = []

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
        assert [step["agent_key"] for step in mock_task.agent_trace] == [
            "profile_context",
            "content_generator",
            "quality_gate",
            "content_reviewer",
        ]
        assert mock_task.agent_trace[-1]["status"] == "completed"

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
    async def test_unit_generation_revises_once_when_reviewer_rejects(self):
        """Reviewer feedback must drive one generator revision and a second review."""
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_task = MagicMock()
        mock_task.id = "unit-task-revision"
        mock_task.target_id = "node-revision"
        mock_task.user_id = "user-revision"
        mock_task.target_metadata = {"path_id": "path-revision", "unit_content_version_id": "ver-revision"}
        mock_task.agent_trace = []

        mock_node = MagicMock(
            title="Python Functions",
            description="Function design",
            difficulty="beginner",
            learning_outcomes='["Define functions"]',
        )
        mock_path = MagicMock(active_version_id="path-version", goal_id=None)
        mock_version = MagicMock(id="ver-revision", unit_content_id="uc-revision", status="generating")
        mock_unit = MagicMock(
            id="uc-revision",
            active_version_id=None,
            status="generating",
            active_task_id="unit-task-revision",
        )
        mock_background_task = MagicMock(status="running")

        def content(section_prefix: str) -> dict[str, object]:
            return {
                "introduction": f"# {section_prefix}",
                "objectives": ["Define functions"],
                "sections": [
                    {
                        "section_id": "sec-1",
                        "title": f"{section_prefix} Basics",
                        "content": f"{section_prefix} content " * 80,
                        "order": 1,
                    },
                    {
                        "section_id": "sec-2",
                        "title": f"{section_prefix} Practice",
                        "content": f"{section_prefix} practice " * 80,
                        "order": 2,
                    },
                ],
                "practice_tasks": [],
                "summary": f"{section_prefix} summary",
                "references": [],
            }

        first_review = {
            "passed": False,
            "score": 45,
            "issues": [{"severity": "error", "description": "缺少边界案例"}],
            "summary": "需要返修",
        }
        second_review = {"passed": True, "score": 91, "issues": [], "summary": "返修通过"}

        def scalar(value):
            result = MagicMock()
            result.scalar_one_or_none.return_value = value
            return result

        call_count = 0

        async def execute(_statement):
            nonlocal call_count
            call_count += 1
            values = {
                1: mock_node,
                2: mock_path,
                3: mock_version,
                4: mock_version,
                5: mock_background_task,
                6: mock_unit,
            }
            return scalar(values.get(call_count))

        mock_db.execute = execute

        with (
            patch("app.workers.tasks.update_task_status", new_callable=AsyncMock),
            patch("app.workers.tasks.asyncio.sleep", new_callable=AsyncMock),
            patch("app.services.llm.llm_json", new_callable=AsyncMock) as mock_llm,
            patch(
                "app.services.profile_merge.load_profile_context",
                new_callable=AsyncMock,
                return_value=(None, ""),
            ),
        ):
            mock_llm.side_effect = [content("Draft"), first_review, content("Revised"), second_review]
            result = await _execute_unit_generation(mock_db, mock_task)

        assert result["node_id"] == "node-revision"
        assert mock_llm.await_count == 4
        assert mock_version.content["generation_metadata"]["source"] == "llm_revision"
        assert mock_version.content["generation_metadata"]["review_iterations"] == 2
        assert mock_version.content["generation_metadata"]["review_score"] == 91
        assert [(step["agent_key"], step["iteration"], step["status"]) for step in mock_task.agent_trace][-3:] == [
            ("content_reviewer", 1, "needs_revision"),
            ("content_generator", 2, "completed"),
            ("content_reviewer", 2, "completed"),
        ]

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
# _execute_lecture_generation
# ---------------------------------------------------------------------------
class TestExecuteLectureGeneration:
    @pytest.mark.asyncio
    async def test_uses_active_unit_content_version_instead_of_legacy_content(self):
        mock_db = AsyncMock()
        mock_db.flush = AsyncMock()

        task = MagicMock()
        task.id = "lecture-task-1"
        task.target_id = "node-1"
        task.user_id = "user-1"
        task.target_metadata = {"path_id": ""}

        unit_content = MagicMock()
        unit_content.content = {
            "introduction": "LEGACY SOURCE",
            "sections": [{"title": "Legacy", "content": "legacy content"}],
        }
        unit_content.active_version_id = "version-active"

        active_version = MagicMock()
        active_version.content = {
            "introduction": "ACTIVE SOURCE",
            "objectives": ["active objective"],
            "sections": [{"title": "Active", "content": "active version content"}],
        }

        node = MagicMock(title="Python basics", difficulty="beginner")
        lecture = MagicMock()

        def scalar_result(value):
            result = MagicMock()
            result.scalar_one_or_none.return_value = value
            return result

        mock_db.execute = AsyncMock(
            side_effect=[
                scalar_result(unit_content),
                scalar_result(active_version),
                scalar_result(node),
                scalar_result(lecture),
            ]
        )

        lecture_data = {
            "introduction": "Generated lecture",
            "sections": [
                {"section_id": "1", "title": "One", "content": "First", "order": 1},
                {"section_id": "2", "title": "Two", "content": "Second", "order": 2},
            ],
            "key_takeaways": [],
            "common_mistakes": [],
            "summary": "Done",
        }

        with (
            patch("app.workers.tasks.update_task_status", new_callable=AsyncMock),
            patch("app.services.llm.llm_json", new_callable=AsyncMock, return_value=lecture_data),
            patch("app.prompts.agents.lecture_generator_user", return_value="lecture prompt") as build_prompt,
        ):
            result = await _execute_lecture_generation(mock_db, task)

        source_summary = build_prompt.call_args.args[3]
        assert "ACTIVE SOURCE" in source_summary
        assert "active version content" in source_summary
        assert "LEGACY SOURCE" not in source_summary
        assert result == {"lecture_id": lecture.id, "node_id": "node-1"}
        assert lecture.content["introduction"] == "ACTIVE SOURCE"
        assert lecture.content["sections"][0]["source_section_id"] == "sec-1"
        assert lecture.content["generation_metadata"]["source"] == "fallback_quality_gate"
        assert lecture.status == "ready"
        assert lecture.active_task_id is None


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
