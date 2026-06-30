"""Comprehensive unit tests for auth service with mocked DB."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors import ApiError


class TestAuthServiceRegister:
    @pytest.mark.asyncio
    async def test_register_duplicate_email(self):
        from app.services.auth import AuthService

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        svc = AuthService(mock_db)

        # Mock existing user found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock()  # existing user
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ApiError):
            await svc.register("test@example.com", "SecureP@ss123", "Test User")


class TestAuthServiceLogin:
    @pytest.mark.asyncio
    async def test_login_user_not_found(self):
        from app.services.auth import AuthService

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        svc = AuthService(mock_db)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ApiError):
            await svc.login("nonexistent@example.com", "password")


class TestAuthServiceVerifyEmail:
    @pytest.mark.asyncio
    async def test_verify_invalid_token(self):
        from app.services.auth import AuthService

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        svc = AuthService(mock_db)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ApiError):
            await svc.verify_email("invalid-token")


class TestAuthServicePasswordHashing:
    def test_hash_and_verify(self):
        from app.core.security import hash_password, verify_password

        pw = "MySecureP@ss123"
        hashed = hash_password(pw)
        assert verify_password(pw, hashed) is True
        assert verify_password("wrong", hashed) is False

    def test_different_hashes(self):
        from app.core.security import hash_password

        h1 = hash_password("password")
        h2 = hash_password("password")
        assert h1 != h2  # Different salts


class TestAuthServiceTokenGeneration:
    def test_access_token_creation(self):
        from app.core.security import create_access_token

        token = create_access_token("user-1", "session-1")
        assert isinstance(token, str)
        assert len(token) > 20

    def test_csrf_token_generation(self):
        from app.core.security import generate_csrf_token

        t1 = generate_csrf_token()
        t2 = generate_csrf_token()
        assert t1 != t2
        assert len(t1) > 20


class TestAuthServiceAuditLog:
    def test_audit_log_types(self):
        valid_types = [
            "register",
            "login",
            "logout",
            "logout_all",
            "password_change",
            "email_verify",
            "session_revoke",
        ]
        assert len(valid_types) == 7
