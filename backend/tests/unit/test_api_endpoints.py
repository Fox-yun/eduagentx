"""Unit tests for API endpoints using test client with mocked DB/Redis."""

import pytest


class TestHealthEndpoints:
    @pytest.mark.asyncio
    async def test_health_live(self, client):
        resp = await client.get("/health/live")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_health_ready_returns_json(self, client):
        resp = await client.get("/health/ready")
        # May return 503 if DB/Redis mocked as unavailable
        assert resp.status_code in (200, 503)


class TestAuthEndpoints:
    @pytest.mark.asyncio
    async def test_get_csrf_token(self, client):
        resp = await client.get("/api/auth/csrf")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_register_validation(self, client):
        resp = await client.post("/api/auth/register", json={})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_login_validation(self, client):
        resp = await client.post("/api/auth/login", json={})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_me_unauthenticated(self, client):
        resp = await client.get("/api/auth/me")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_unauthenticated(self, client):
        resp = await client.post("/api/auth/refresh")
        # May return 401, 422, or 403 depending on cookie validation
        assert resp.status_code in (401, 403, 422)

    @pytest.mark.asyncio
    async def test_logout_unauthenticated(self, client):
        resp = await client.post("/api/auth/logout")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_verify_email_validation(self, client):
        resp = await client.post("/api/auth/verify-email", json={})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_forgot_password_validation(self, client):
        resp = await client.post("/api/auth/forgot-password", json={})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_reset_password_validation(self, client):
        resp = await client.post("/api/auth/reset-password", json={})
        assert resp.status_code == 422


class TestUserEndpoints:
    @pytest.mark.asyncio
    async def test_get_me_unauthenticated(self, client):
        resp = await client.get("/api/users/me")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_update_me_unauthenticated(self, client):
        resp = await client.patch("/api/users/me", json={"display_name": "Test"})
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_onboarding_unauthenticated(self, client):
        resp = await client.post("/api/users/me/onboarding", json={})
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_change_password_unauthenticated(self, client):
        resp = await client.put("/api/users/me/password", json={})
        assert resp.status_code in (401, 403, 422)


class TestGoalEndpoints:
    @pytest.mark.asyncio
    async def test_list_goals_unauthenticated(self, client):
        resp = await client.get("/api/learning-goals")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_create_goal_unauthenticated(self, client):
        resp = await client.post("/api/learning-goals", json={"title": "test"})
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_get_goal_unauthenticated(self, client):
        resp = await client.get("/api/learning-goals/nonexistent")
        assert resp.status_code == 401


class TestTaskEndpoints:
    @pytest.mark.asyncio
    async def test_list_tasks_unauthenticated(self, client):
        resp = await client.get("/api/tasks")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_task_unauthenticated(self, client):
        resp = await client.get("/api/tasks/nonexistent")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_cancel_task_unauthenticated(self, client):
        resp = await client.post("/api/tasks/nonexistent/cancel")
        assert resp.status_code in (401, 403)


class TestPathEndpoints:
    @pytest.mark.asyncio
    async def test_get_path_unauthenticated(self, client):
        resp = await client.get("/api/learning-paths/nonexistent")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_activate_path_unauthenticated(self, client):
        resp = await client.post("/api/learning-paths/nonexistent/activate")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_revision_request_unauthenticated(self, client):
        resp = await client.post("/api/learning-paths/nonexistent/revision-requests", json={"reason": "test"})
        assert resp.status_code in (401, 403)


class TestResumeEndpoints:
    @pytest.mark.asyncio
    async def test_get_resume_unauthenticated(self, client):
        resp = await client.get("/api/learning/resume")
        assert resp.status_code == 401


class TestKnowledgeEndpoints:
    @pytest.mark.asyncio
    async def test_list_documents_unauthenticated(self, client):
        resp = await client.get("/api/knowledge/documents")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_search_unauthenticated(self, client):
        resp = await client.get("/api/knowledge/search?q=test")
        assert resp.status_code == 401


class TestUnitEndpoints:
    @pytest.mark.asyncio
    async def test_get_content_unauthenticated(self, client):
        resp = await client.get("/api/learning-paths/p1/nodes/n1/content")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_generate_content_unauthenticated(self, client):
        resp = await client.post("/api/learning-paths/p1/nodes/n1/content")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_create_assessment_unauthenticated(self, client):
        resp = await client.post("/api/learning-paths/p1/nodes/n1/assessments")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_create_practice_unauthenticated(self, client):
        resp = await client.post("/api/learning-paths/p1/nodes/n1/practice")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_submit_assessment_unauthenticated(self, client):
        resp = await client.post("/api/assessments/a1/submit", json={"answers": {}})
        assert resp.status_code in (401, 403)


class TestChatEndpoints:
    @pytest.mark.asyncio
    async def test_chat_unauthenticated(self, client):
        resp = await client.post(
            "/api/chat",
            json={
                "question": "What is X?",
                "node_id": "n1",
                "path_id": "p1",
            },
        )
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_chat_validation(self, client):
        resp = await client.post("/api/chat", json={})
        assert resp.status_code in (401, 403, 422)


class TestClarificationEndpoints:
    @pytest.mark.asyncio
    async def test_get_clarifications_unauthenticated(self, client):
        resp = await client.get("/api/learning-goals/g1/clarifications")
        assert resp.status_code == 401


class TestDiagnosticEndpoints:
    @pytest.mark.asyncio
    async def test_get_diagnostic_unauthenticated(self, client):
        resp = await client.get("/api/learning-goals/g1/diagnostic")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_submit_diagnostic_unauthenticated(self, client):
        resp = await client.post("/api/learning-goals/g1/diagnostic/submit", json={"answers": {}})
        assert resp.status_code in (401, 403)
