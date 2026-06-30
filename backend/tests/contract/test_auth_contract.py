"""Auth API contract tests - verify DTO shapes match frontend expectations."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client() -> TestClient:
    """Create a test client."""
    app = create_app()
    return TestClient(app)


class TestRegisterContract:
    """Test register endpoint contract."""

    def test_register_requires_accept_terms(self, client: TestClient) -> None:
        """Register without accept_terms should fail validation."""
        response = client.post(
            "/api/auth/register",
            json={
                "email": "test@example.com",
                "password": "StrongPass123!",
                "display_name": "Test User",
            },
        )
        assert response.status_code == 422

    def test_register_rejects_extra_fields(self, client: TestClient) -> None:
        """Register with extra fields should fail validation."""
        response = client.post(
            "/api/auth/register",
            json={
                "email": "test@example.com",
                "password": "StrongPass123!",
                "display_name": "Test User",
                "accept_terms": True,
                "extra_field": "should_fail",
            },
        )
        assert response.status_code == 422

    def test_register_accept_terms_must_be_true(self, client: TestClient) -> None:
        """accept_terms=False should fail validation."""
        response = client.post(
            "/api/auth/register",
            json={
                "email": "test@example.com",
                "password": "StrongPass123!",
                "display_name": "Test User",
                "accept_terms": False,
            },
        )
        assert response.status_code == 422


class TestLoginContract:
    """Test login endpoint contract."""

    def test_login_rejects_extra_fields(self, client: TestClient) -> None:
        """Login with extra fields should fail validation."""
        response = client.post(
            "/api/auth/login",
            json={
                "email": "test@example.com",
                "password": "password",
                "extra_field": "should_fail",
            },
        )
        assert response.status_code == 422

    def test_login_accepts_remember_me(self) -> None:
        """LoginRequest DTO should accept remember_me field without requiring DB."""
        from app.routers.auth import LoginRequest

        request = LoginRequest(
            email="user@example.com",
            password="Password123!",
            remember_me=True,
        )
        assert request.remember_me is True


class TestPasswordResetContract:
    """Test password reset endpoint contract."""

    def test_reset_password_uses_password_field(self, client: TestClient) -> None:
        """Reset password should accept 'password' not 'new_password'."""
        response = client.post(
            "/api/auth/reset-password",
            json={
                "token": "some-token",
                "password": "NewStrongPass123!",
            },
        )
        # Should not fail schema validation
        assert response.status_code != 422 or "password" not in response.text.lower()


class TestCSRFContract:
    """Test CSRF protection contract."""

    def test_refresh_requires_csrf(self, client: TestClient) -> None:
        """Refresh endpoint should require CSRF token."""
        response = client.post("/api/auth/refresh")
        # Without CSRF token, should get 403
        assert response.status_code in (401, 403)

    def test_logout_requires_csrf(self, client: TestClient) -> None:
        """Logout endpoint should require CSRF token."""
        response = client.post("/api/auth/logout")
        assert response.status_code in (401, 403)

    def test_csrf_endpoint_exempt(self, client: TestClient) -> None:
        """CSRF endpoint itself should be exempt from CSRF."""
        response = client.get("/api/auth/csrf")
        assert response.status_code == 200
        assert "csrf_token" in response.json()


class TestSessionContract:
    """Test session endpoints contract."""

    def test_sessions_requires_auth(self, client: TestClient) -> None:
        """Sessions endpoint should require authentication."""
        response = client.get("/api/auth/sessions")
        assert response.status_code == 401

    def test_logout_all_requires_auth(self, client: TestClient) -> None:
        """Logout-all endpoint should require authentication."""
        response = client.post("/api/auth/logout-all")
        assert response.status_code in (401, 403)

    def test_change_password_requires_auth(self, client: TestClient) -> None:
        """Change password endpoint should require authentication."""
        response = client.post(
            "/api/auth/change-password",
            json={"current_password": "old", "new_password": "NewPass123!"},
        )
        assert response.status_code in (401, 403)
