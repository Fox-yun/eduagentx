"""Comprehensive unit tests for clarifications router."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_goal(**overrides):
    g = MagicMock()
    g.id = overrides.get("id", "goal-1")
    g.user_id = overrides.get("user_id", "user-1")
    g.status = overrides.get("status", "draft")
    return g


def _make_clar_set(**overrides):
    s = MagicMock()
    s.id = overrides.get("id", "clar-set-1")
    s.goal_id = overrides.get("goal_id", "goal-1")
    s.status = overrides.get("status", "active")
    return s


def _make_clar_question(**overrides):
    q = MagicMock()
    q.id = overrides.get("id", "q-1")
    q.set_id = overrides.get("set_id", "clar-set-1")
    q.question_type = overrides.get("question_type", "single_choice")
    q.prompt = overrides.get("prompt", "What is your level?")
    q.required = overrides.get("required", True)
    q.options = overrides.get("options", [{"value": "beginner", "label": "Beginner"}])
    q.min_value = overrides.get("min_value")
    q.max_value = overrides.get("max_value")
    q.question_order = overrides.get("question_order", 1)
    return q


def _mock_scalar_result(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _mock_scalars(items):
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


@pytest.fixture
def app_with_mocked_auth():
    app = FastAPI()

    # Register error handlers so ApiError returns proper status codes
    from app.core.errors import register_error_handlers

    register_error_handlers(app)

    mock_user = MagicMock()
    mock_user.id = "user-1"

    from app.routers.clarifications import router

    app.include_router(router, prefix="/goals")

    from app.core.auth_deps import require_learning_user
    from app.core.database import get_db

    async def override_auth():
        return mock_user

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


class TestGetClarifications:
    def test_get_existing_clarifications(self, app_with_mocked_auth):
        app, mock_db = app_with_mocked_auth

        goal = _make_goal()
        clar_set = _make_clar_set()
        question = _make_clar_question()

        with patch("app.routers.clarifications.GoalService") as MockGoalSvc, patch("app.routers.clarifications.select"):
            goal_svc = MockGoalSvc.return_value
            goal_svc.get_goal = AsyncMock(return_value=goal)

            call_count = 0

            async def execute_side_effect(query):
                nonlocal call_count
                call_count += 1
                if call_count == 1:  # clarification set
                    return _mock_scalar_result(clar_set)
                elif call_count == 2:  # questions
                    return _mock_scalars([question])
                elif call_count == 3:  # answers
                    return _mock_scalars([])
                return _mock_scalar_result(None)

            mock_db.execute = AsyncMock(side_effect=execute_side_effect)

            client = TestClient(app)
            resp = client.get("/goals/goal-1/clarifications")
            assert resp.status_code == 200
            data = resp.json()
            assert "questions" in data
            assert len(data["questions"]) == 1

    def test_get_clarifications_creates_defaults(self, app_with_mocked_auth):
        app, mock_db = app_with_mocked_auth

        goal = _make_goal()

        with patch("app.routers.clarifications.GoalService") as MockGoalSvc:
            goal_svc = MockGoalSvc.return_value
            goal_svc.get_goal = AsyncMock(return_value=goal)

            call_count = 0

            async def execute_side_effect(query):
                nonlocal call_count
                call_count += 1
                if call_count == 1:  # no existing clarification set
                    return _mock_scalar_result(None)
                # After creating set and questions, query them
                return _mock_scalars([])

            mock_db.execute = AsyncMock(side_effect=execute_side_effect)

            client = TestClient(app)
            resp = client.get("/goals/goal-1/clarifications")
            assert resp.status_code == 200
            # Should have added the default questions
            assert mock_db.add.called


class TestSubmitClarifications:
    def test_submit_clarifications_success(self, app_with_mocked_auth):
        app, mock_db = app_with_mocked_auth

        goal = _make_goal()
        clar_set = _make_clar_set()
        question = _make_clar_question()

        with (
            patch("app.routers.clarifications.GoalService") as MockGoalSvc,
            patch(
                "app.routers.clarifications._pregenerate_diagnostic_questions",
                new_callable=AsyncMock,
            ) as mock_pregenerate,
        ):
            goal_svc = MockGoalSvc.return_value
            goal_svc.get_goal = AsyncMock(return_value=goal)
            goal_svc.transition_goal = AsyncMock(return_value=goal)

            call_count = 0

            async def execute_side_effect(query):
                nonlocal call_count
                call_count += 1
                if call_count == 1:  # clarification set
                    return _mock_scalar_result(clar_set)
                elif call_count == 2:  # questions
                    return _mock_scalars([question])
                elif call_count == 3:  # existing answer check
                    return _mock_scalar_result(None)
                return _mock_scalar_result(None)

            mock_db.execute = AsyncMock(side_effect=execute_side_effect)

            client = TestClient(app)
            resp = client.post(
                "/goals/goal-1/clarifications",
                json={"answers": {"q-1": "beginner"}},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["next_step"] == "diagnostic"
            mock_pregenerate.assert_awaited_once_with("goal-1", "user-1")

    def test_submit_no_clarification_set(self, app_with_mocked_auth):
        app, mock_db = app_with_mocked_auth

        goal = _make_goal()

        with (
            patch("app.routers.clarifications.GoalService") as MockGoalSvc,
            patch(
                "app.routers.clarifications._pregenerate_diagnostic_questions",
                new_callable=AsyncMock,
            ),
        ):
            goal_svc = MockGoalSvc.return_value
            goal_svc.get_goal = AsyncMock(return_value=goal)

            mock_db.execute = AsyncMock(return_value=_mock_scalar_result(None))

            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post(
                "/goals/goal-1/clarifications",
                json={"answers": {"q-1": "beginner"}},
            )
            assert resp.status_code == 404

    def test_submit_updates_existing_answer(self, app_with_mocked_auth):
        app, mock_db = app_with_mocked_auth

        goal = _make_goal()
        clar_set = _make_clar_set()
        question = _make_clar_question()
        existing_answer = MagicMock()
        existing_answer.answer_value = '"old_value"'

        with (
            patch("app.routers.clarifications.GoalService") as MockGoalSvc,
            patch(
                "app.routers.clarifications._pregenerate_diagnostic_questions",
                new_callable=AsyncMock,
            ),
        ):
            goal_svc = MockGoalSvc.return_value
            goal_svc.get_goal = AsyncMock(return_value=goal)
            goal_svc.transition_goal = AsyncMock(return_value=goal)

            call_count = 0

            async def execute_side_effect(query):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return _mock_scalar_result(clar_set)
                elif call_count == 2:
                    return _mock_scalars([question])
                elif call_count == 3:
                    return _mock_scalar_result(existing_answer)
                return _mock_scalar_result(None)

            mock_db.execute = AsyncMock(side_effect=execute_side_effect)

            client = TestClient(app)
            resp = client.post(
                "/goals/goal-1/clarifications",
                json={"answers": {"q-1": "intermediate"}},
            )
            assert resp.status_code == 200
