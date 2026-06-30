"""Comprehensive unit tests for diagnostics router."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_goal(**overrides):
    g = MagicMock()
    g.id = overrides.get("id", "goal-1")
    g.user_id = overrides.get("user_id", "user-1")
    g.title = overrides.get("title", "Learn Python")
    g.raw_description = overrides.get("raw_description", "Learn Python from scratch")
    g.normalized_goal = overrides.get("normalized_goal")
    g.status = overrides.get("status", "diagnosing")
    return g


def _make_task(**overrides):
    t = MagicMock()
    t.id = overrides.get("id", "task-1")
    return t


def _mock_scalar_result(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _mock_scalars_result(*values):
    r = MagicMock()
    r.scalars.return_value.all.return_value = list(values)
    return r


class MockDbSession:
    """A test double for AsyncSession that tracks added objects."""

    def __init__(self):
        self.added = []
        self.execute_results: dict = {}
        self._default_result = _mock_scalar_result(None)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass

    async def commit(self):
        pass

    async def refresh(self, obj):
        pass

    async def execute(self, stmt):
        # Check if we have a specific result for this query
        # by matching the table being queried
        table_name = ""
        stmt_str = str(stmt)
        for table in [
            "diagnostic_attempts",
            "diagnostic_answers",
            "diagnostic_results",
            "background_tasks",
            "learning_goals",
        ]:
            if table in stmt_str:
                table_name = table
                break
        if table_name in self.execute_results:
            return self.execute_results[table_name]
        if "FOR UPDATE" in stmt_str:
            return self.execute_results.get("for_update", self._default_result)
        return self._default_result

    def set_result(self, table: str, result):
        self.execute_results[table] = result

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


@pytest.fixture
def app_with_mocked_auth():
    app = FastAPI()

    from app.core.errors import register_error_handlers

    register_error_handlers(app)

    mock_user = MagicMock()
    mock_user.id = "user-1"

    from app.core.auth_deps import require_learning_user
    from app.core.database import get_db
    from app.routers.diagnostics import router

    app.include_router(router, prefix="/goals")

    async def override_auth():
        return mock_user

    mock_db = MockDbSession()

    async def override_db():
        return mock_db

    app.dependency_overrides[require_learning_user] = override_auth
    app.dependency_overrides[get_db] = override_db

    return app, mock_db


class TestGetDiagnostic:
    def test_get_diagnostic(self, app_with_mocked_auth):
        app, mock_db = app_with_mocked_auth
        mock_db.set_result("diagnostic_attempts", _mock_scalar_result(None))

        goal = _make_goal()

        with patch("app.routers.diagnostics.GoalService") as MockGoalSvc:
            goal_svc = MockGoalSvc.return_value
            goal_svc.get_goal = AsyncMock(return_value=goal)

            client = TestClient(app)
            resp = client.get("/goals/goal-1/diagnostic")
            assert resp.status_code == 200
            data = resp.json()
            assert data["goal_id"] == "goal-1"
            assert len(data["questions"]) > 0
            assert data["status"] == "draft"
            assert "attempt_id" in data

    def test_get_diagnostic_programming_topic(self, app_with_mocked_auth):
        app, mock_db = app_with_mocked_auth
        mock_db.set_result("diagnostic_attempts", _mock_scalar_result(None))

        goal = _make_goal(raw_description="Learn Python programming")

        with patch("app.routers.diagnostics.GoalService") as MockGoalSvc:
            goal_svc = MockGoalSvc.return_value
            goal_svc.get_goal = AsyncMock(return_value=goal)

            client = TestClient(app)
            resp = client.get("/goals/goal-1/diagnostic")
            data = resp.json()
            prompts = [q["prompt"] for q in data["questions"]]
            assert any("BFS" in p or "广度优先" in p for p in prompts)

    def test_get_diagnostic_ml_topic(self, app_with_mocked_auth):
        app, mock_db = app_with_mocked_auth
        mock_db.set_result("diagnostic_attempts", _mock_scalar_result(None))

        goal = _make_goal(raw_description="Learn machine learning and neural networks")

        with patch("app.routers.diagnostics.GoalService") as MockGoalSvc:
            goal_svc = MockGoalSvc.return_value
            goal_svc.get_goal = AsyncMock(return_value=goal)

            client = TestClient(app)
            resp = client.get("/goals/goal-1/diagnostic")
            data = resp.json()
            prompts = [q["prompt"] for q in data["questions"]]
            assert any("监督学习" in p or "过拟合" in p for p in prompts)

    def test_get_diagnostic_math_topic(self, app_with_mocked_auth):
        app, mock_db = app_with_mocked_auth
        mock_db.set_result("diagnostic_attempts", _mock_scalar_result(None))

        goal = _make_goal(raw_description="Study calculus and probability")

        with patch("app.routers.diagnostics.GoalService") as MockGoalSvc:
            goal_svc = MockGoalSvc.return_value
            goal_svc.get_goal = AsyncMock(return_value=goal)

            client = TestClient(app)
            resp = client.get("/goals/goal-1/diagnostic")
            data = resp.json()
            prompts = [q["prompt"] for q in data["questions"]]
            assert any("矩阵" in p or "导数" in p for p in prompts)

    def test_get_diagnostic_general_topic(self, app_with_mocked_auth):
        app, mock_db = app_with_mocked_auth
        mock_db.set_result("diagnostic_attempts", _mock_scalar_result(None))

        goal = _make_goal(raw_description="Learn something completely different")

        with patch("app.routers.diagnostics.GoalService") as MockGoalSvc:
            goal_svc = MockGoalSvc.return_value
            goal_svc.get_goal = AsyncMock(return_value=goal)

            client = TestClient(app)
            resp = client.get("/goals/goal-1/diagnostic")
            data = resp.json()
            assert len(data["questions"]) >= 2


class TestSubmitDiagnostic:
    def test_submit_diagnostic(self, app_with_mocked_auth):
        app, mock_db = app_with_mocked_auth

        goal = _make_goal()
        task = _make_task()

        # Mock FOR UPDATE lookup to return a draft attempt
        mock_attempt = MagicMock()
        mock_attempt.id = "attempt-1"
        mock_attempt.diagnostic_id = "diag-goal-1"
        mock_attempt.goal_id = "goal-1"
        mock_attempt.user_id = "user-1"
        mock_attempt.status = "draft"
        mock_db.set_result("for_update", _mock_scalar_result(mock_attempt))

        with (
            patch("app.routers.diagnostics.GoalService") as MockGoalSvc,
            patch("app.routers.diagnostics.TaskService") as MockTaskSvc,
        ):
            goal_svc = MockGoalSvc.return_value
            goal_svc.get_goal = AsyncMock(return_value=goal)

            task_svc = MockTaskSvc.return_value
            task_svc.create_task = AsyncMock(return_value=task)

            client = TestClient(app)
            resp = client.post(
                "/goals/goal-1/diagnostic/submit",
                json={
                    "attempt_id": "attempt-1",
                    "answers": [
                        {"question_id": "diag-goal-1-3", "answer": ["a", "c", "d"]},
                    ],
                },
            )
            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert "task_id" in data
            assert data["status"] == "grading"

    def test_submit_diagnostic_invalid_attempt(self, app_with_mocked_auth):
        app, mock_db = app_with_mocked_auth

        # No attempt found
        mock_db.set_result("for_update", _mock_scalar_result(None))

        client = TestClient(app)
        resp = client.post(
            "/goals/goal-1/diagnostic/submit",
            json={"attempt_id": "invalid-id", "answers": []},
        )
        assert resp.status_code == 404


class TestDetectTopic:
    def test_detect_programming(self):
        from app.routers.diagnostics import _detect_topic

        goal = MagicMock()
        goal.raw_description = "Learn Python programming basics"
        goal.normalized_goal = None
        assert _detect_topic(goal) == "programming"

    def test_detect_math(self):
        from app.routers.diagnostics import _detect_topic

        goal = MagicMock()
        goal.raw_description = "Study linear algebra and calculus"
        goal.normalized_goal = None
        assert _detect_topic(goal) == "mathematics"

    def test_detect_ml(self):
        from app.routers.diagnostics import _detect_topic

        goal = MagicMock()
        goal.raw_description = "Deep learning with neural networks"
        goal.normalized_goal = None
        assert _detect_topic(goal) == "machine_learning"

    def test_detect_general(self):
        from app.routers.diagnostics import _detect_topic

        goal = MagicMock()
        goal.raw_description = "Cook Italian food"
        goal.normalized_goal = None
        assert _detect_topic(goal) == "general"
