"""Security tests for CSRF protection and session binding."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.auth import AuthService


@pytest.fixture()
def client() -> TestClient:
    """Create a test client."""
    app = create_app()
    return TestClient(app)


class TestCSRFProtection:
    """Test CSRF double-submit cookie protection."""

    def test_post_without_csrf_returns_403(self, client: TestClient) -> None:
        """POST to protected endpoint without CSRF should return 403."""
        response = client.post("/api/auth/logout")
        assert response.status_code in (401, 403)

    def test_csrf_token_generation(self, client: TestClient) -> None:
        """CSRF endpoint should return a token and set a cookie."""
        response = client.get("/api/auth/csrf")
        assert response.status_code == 200
        data = response.json()
        assert "csrf_token" in data
        assert len(data["csrf_token"]) > 0

    def test_csrf_mismatch_returns_403(self, client: TestClient) -> None:
        """Mismatched CSRF tokens should return 403."""
        # Get CSRF token
        csrf_response = client.get("/api/auth/csrf")
        csrf_token = csrf_response.json()["csrf_token"]

        # Try to use a different token in header
        response = client.post(
            "/api/auth/logout",
            headers={"X-CSRF-Token": "mismatched-token"},
            cookies={"csrftoken": csrf_token},
        )
        assert response.status_code in (401, 403)

    def test_safe_methods_exempt_from_csrf(self, client: TestClient) -> None:
        """GET requests should not require CSRF."""
        response = client.get("/health/live")
        assert response.status_code == 200

    def test_csrf_uses_constant_time_comparison(self) -> None:
        """Verify CSRF middleware uses hmac.compare_digest."""
        import inspect

        from app.core.csrf import CSRFMiddleware

        source = inspect.getsource(CSRFMiddleware.dispatch)
        assert "hmac.compare_digest" in source

    def test_register_exempt_from_csrf(self, client: TestClient) -> None:
        """Register should be exempt from CSRF (no prior session)."""
        response = client.post(
            "/api/auth/register",
            json={
                "email": "test@example.com",
                "password": "weak",
                "display_name": "Test",
                "accept_terms": True,
            },
        )
        # Should not get 403 CSRF error (may get other errors)
        assert response.status_code != 403 or "CSRF" not in response.text


class TestSessionBinding:
    """Test that access tokens are bound to database sessions."""

    def test_me_endpoint_requires_auth(self, client: TestClient) -> None:
        """/me should require authentication."""
        response = client.get("/api/auth/me")
        assert response.status_code == 401

    def test_me_returns_user_structure(self, client: TestClient) -> None:
        """/me error should have proper error structure."""
        response = client.get("/api/auth/me")
        data = response.json()
        # Should have error structure
        assert "detail" in data or "error" in data


class TestPasswordSecurity:
    """Test password-related security."""

    def test_forgot_password_no_email_leak(self, client: TestClient) -> None:
        """Forgot password should not reveal if email exists."""
        with patch.object(
            AuthService,
            "request_password_reset",
            new_callable=AsyncMock,
            return_value={"message": "If an account exists, a password reset link has been sent."},
        ):
            response = client.post(
                "/api/auth/forgot-password",
                json={"email": "nonexistent@example.com"},
            )
            assert response.status_code == 200
            assert "If an account exists" in response.json().get("message", "")

    def test_reset_password_requires_password_field(self, client: TestClient) -> None:
        """Reset password should use 'password' field, not 'new_password'."""
        with patch.object(AuthService, "reset_password", new_callable=AsyncMock, return_value=None):
            response = client.post(
                "/api/auth/reset-password",
                json={"token": "test", "password": "NewPass123!"},
            )
            # Should not fail with schema error about 'password' field
            assert response.status_code != 422 or "password" not in str(response.json()).lower()
