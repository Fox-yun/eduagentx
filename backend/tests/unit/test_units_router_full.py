"""Comprehensive unit tests for units router."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_mocked_auth():
    app = FastAPI()
    mock_user = MagicMock()
    mock_user.id = "user-1"

    from app.routers.units import router

    app.include_router(router, prefix="/paths")

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


class TestGetUnitContent:
    def test_get_unit_content(self, app_with_mocked_auth):
        app, mock_db = app_with_mocked_auth

        content = {
            "unit_id": "u1",
            "path_id": "path-1",
            "path_version": 1,
            "node_id": "node-1",
            "content_version": 1,
            "status": "ready",
            "active_task_id": None,
            "introduction": "Intro",
            "objectives": ["Obj1"],
            "sections": [],
            "practice_tasks": [],
            "summary": "Sum",
            "references": [],
            "error": None,
        }

        with patch("app.routers.units.UnitService") as MockSvc:
            instance = MockSvc.return_value
            instance.get_unit_content = AsyncMock(return_value=content)

            client = TestClient(app)
            resp = client.get("/paths/path-1/nodes/node-1/content")
            assert resp.status_code == 200
            data = resp.json()
            assert data["unit_id"] == "u1"
            assert data["status"] == "ready"


class TestGenerateUnitContent:
    def test_generate_unit_content(self, app_with_mocked_auth):
        app, mock_db = app_with_mocked_auth

        task = MagicMock()
        task.id = "task-1"

        with patch("app.services.task.TaskService") as MockTaskSvc:
            task_svc = MockTaskSvc.return_value
            task_svc.create_task = AsyncMock(return_value=task)

            client = TestClient(app)
            resp = client.post("/paths/path-1/nodes/node-1/content")
            assert resp.status_code == 200
            data = resp.json()
            assert data["next_step"] == "generating"
            assert data["active_task_id"] == "task-1"


class TestCreateAssessment:
    def test_create_assessment(self, app_with_mocked_auth):
        app, mock_db = app_with_mocked_auth

        assessment = {
            "assessment_id": "assess-1",
            "path_id": "path-1",
            "node_id": "node-1",
            "status": "pending",
            "questions": [],
        }

        with patch("app.routers.units.UnitService") as MockSvc:
            instance = MockSvc.return_value
            instance.create_assessment = AsyncMock(return_value=assessment)

            client = TestClient(app)
            resp = client.post("/paths/path-1/nodes/node-1/assessments")
            assert resp.status_code == 200
            data = resp.json()
            assert data["assessment_id"] == "assess-1"


class TestCreatePractice:
    def test_create_practice(self, app_with_mocked_auth):
        app, mock_db = app_with_mocked_auth

        practice = {
            "node_id": "node-1",
            "questions": [
                {"question_id": "practice-1", "type": "single_choice", "prompt": "Q1"},
            ],
        }

        with patch("app.routers.units.UnitService") as MockSvc:
            instance = MockSvc.return_value
            instance.create_practice = AsyncMock(return_value=practice)

            client = TestClient(app)
            resp = client.post("/paths/path-1/nodes/node-1/practice")
            assert resp.status_code == 200
            data = resp.json()
            assert data["node_id"] == "node-1"
            assert len(data["questions"]) == 1


class TestSubmitAssessment:
    def test_submit_assessment_function_exists(self):
        """Verify the submit_assessment function is importable."""
        from app.routers.units import submit_assessment

        assert submit_assessment is not None
