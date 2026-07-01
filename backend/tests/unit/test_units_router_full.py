"""Comprehensive unit tests for units router.

Uses httpx.AsyncClient for httpx 0.28+ compatibility with async endpoints.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


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

    async def override_db():
        return mock_db

    app.dependency_overrides[require_learning_user] = override_auth
    app.dependency_overrides[get_db] = override_db

    return app, mock_db


@pytest.fixture(autouse=True)
def _patch_node_access():
    """Patch require_node_access in the units router module."""
    with patch("app.routers.units.require_node_access", AsyncMock(return_value=None)):
        yield


class TestGetUnitContent:
    @pytest.mark.asyncio
    async def test_get_unit_content(self, app_with_mocked_auth):
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

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/paths/path-1/nodes/node-1/content")
                assert resp.status_code == 200
                data = resp.json()
                assert data["unit_id"] == "u1"
                assert data["status"] == "ready"


class TestGenerateUnitContent:
    @pytest.mark.asyncio
    async def test_generate_unit_content(self, app_with_mocked_auth):
        app, mock_db = app_with_mocked_auth

        result = {"next_step": "generating", "active_task_id": "task-1"}

        with patch("app.routers.units.UnitService") as MockSvc:
            instance = MockSvc.return_value
            instance.generate_content = AsyncMock(return_value=result)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/paths/path-1/nodes/node-1/content")
                assert resp.status_code == 200
                data = resp.json()
                assert data["next_step"] == "generating"
                assert data["active_task_id"] == "task-1"


class TestCreateAssessment:
    @pytest.mark.asyncio
    async def test_create_assessment(self, app_with_mocked_auth):
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

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/paths/path-1/nodes/node-1/assessments")
                assert resp.status_code == 200
                data = resp.json()
                assert data["assessment_id"] == "assess-1"


class TestCreatePractice:
    @pytest.mark.asyncio
    async def test_create_practice(self, app_with_mocked_auth):
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

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/paths/path-1/nodes/node-1/practice")
                assert resp.status_code == 200
                data = resp.json()
                assert data["node_id"] == "node-1"
                assert len(data["questions"]) == 1


class TestSubmitAssessment:
    def test_submit_assessment_function_exists(self):
        """Verify the submit_assessment function is importable."""
        from app.routers.units import submit_assessment

        assert submit_assessment is not None
