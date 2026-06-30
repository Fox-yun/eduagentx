"""Comprehensive unit tests for AuthService."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.errors import ApiError


def _mock_scalar_result(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _make_user(**overrides):
    u = MagicMock()
    u.id = overrides.get("id", "user-1")
    u.email = overrides.get("email", "test@example.com")
    u.email_normalized = overrides.get("email_normalized", "test@example.com")
    u.display_name = overrides.get("display_name", "Test User")
    u.password_hash = overrides.get("password_hash", "hashed_pw")
    u.status = overrides.get("status", "active")
    u.email_verified_at = overrides.get("email_verified_at", datetime.now(UTC))
    u.failed_login_count = overrides.get("failed_login_count", 0)
    u.locked_until = overrides.get("locked_until")
    u.last_login_at = overrides.get("last_login_at")
    return u


def _make_verification(**overrides):
    v = MagicMock()
    v.id = overrides.get("id", "v-1")
    v.user_id = overrides.get("user_id", "user-1")
    v.purpose = overrides.get("purpose", "email_verification")
    v.token_hash = overrides.get("token_hash", "hash123")
    v.expires_at = overrides.get("expires_at", datetime.now(UTC) + timedelta(hours=24))
    v.used_at = overrides.get("used_at")
    return v


def _make_refresh_token(**overrides):
    t = MagicMock()
    t.id = overrides.get("id", "rt-1")
    t.session_id = overrides.get("session_id", "sess-1")
    t.token_family_id = overrides.get("token_family_id", "family-1")
    t.token_hash = overrides.get("token_hash", "hash123")
    t.jti = overrides.get("jti", "jti-1")
    t.parent_jti = overrides.get("parent_jti")
    t.replaced_by_jti = overrides.get("replaced_by_jti")
    t.issued_at = overrides.get("issued_at", datetime.now(UTC))
    t.expires_at = overrides.get("expires_at", datetime.now(UTC) + timedelta(days=30))
    t.used_at = overrides.get("used_at")
    t.revoked_at = overrides.get("revoked_at")
    t.token_family_id = overrides.get("token_family_id", "family-1")
    return t


def _make_session(**overrides):
    s = MagicMock()
    s.id = overrides.get("id", "sess-1")
    s.user_id = overrides.get("user_id", "user-1")
    s.revoked_at = overrides.get("revoked_at")
    s.last_used_at = overrides.get("last_used_at", datetime.now(UTC))
    s.ip_address = overrides.get("ip_address")
    s.user_agent = overrides.get("user_agent")
    s.refresh_token_hash = "hash"
    s.refresh_token_jti = "jti"
    return s


class TestAuthServiceRegister:
    @pytest.mark.asyncio
    async def test_register_duplicate_email(self):
        from app.services.auth import AuthService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = AuthService(db)
        db.execute = AsyncMock(return_value=_mock_scalar_result(_make_user()))

        with pytest.raises(ApiError) as exc_info:
            await svc.register("test@example.com", "SecureP@ss123", "Test User")
        assert exc_info.value.code == "EMAIL_EXISTS"

    @pytest.mark.asyncio
    async def test_register_weak_password(self):
        from app.services.auth import AuthService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = AuthService(db)

        with pytest.raises(ApiError) as exc_info:
            await svc.register("test@example.com", "short", "Test User")
        assert exc_info.value.code == "WEAK_PASSWORD"

    @pytest.mark.asyncio
    async def test_register_common_password(self):
        from app.services.auth import AuthService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = AuthService(db)

        with pytest.raises(ApiError) as exc_info:
            await svc.register("test@example.com", "password1234", "Test User")
        assert exc_info.value.code == "WEAK_PASSWORD"

    @pytest.mark.asyncio
    async def test_register_happy_path_dev(self):
        from app.services.auth import AuthService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = AuthService(db)
        db.execute = AsyncMock(return_value=_mock_scalar_result(None))  # no existing user

        with patch("app.services.auth.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(app_env="development")

            result = await svc.register("test@example.com", "SecureP@ss123!", "Test User")
            assert result["user"] is not None
            assert result["verification_token"] is None  # dev mode skips verification
            assert result["next_step"] == "login"
            db.add.assert_called()
            db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_register_production_creates_verification(self):
        from app.services.auth import AuthService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = AuthService(db)
        db.execute = AsyncMock(return_value=_mock_scalar_result(None))

        with patch("app.services.auth.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(app_env="production")

            result = await svc.register("test@example.com", "SecureP@ss123!", "Test User")
            assert result["verification_token"] is not None
            assert result["next_step"] == "verify_email"


class TestAuthServiceVerifyEmail:
    @pytest.mark.asyncio
    async def test_verify_invalid_token(self):
        from app.services.auth import AuthService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = AuthService(db)
        db.execute = AsyncMock(return_value=_mock_scalar_result(None))

        with pytest.raises(ApiError) as exc_info:
            await svc.verify_email("invalid-token")
        assert exc_info.value.code == "INVALID_TOKEN"

    @pytest.mark.asyncio
    async def test_verify_expired_token(self):
        from app.services.auth import AuthService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = AuthService(db)
        verification = _make_verification(expires_at=datetime.now(UTC) - timedelta(hours=1))
        db.execute = AsyncMock(return_value=_mock_scalar_result(verification))

        with pytest.raises(ApiError) as exc_info:
            await svc.verify_email("token")
        assert exc_info.value.code == "TOKEN_EXPIRED"

    @pytest.mark.asyncio
    async def test_verify_success(self):
        from app.services.auth import AuthService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = AuthService(db)
        verification = _make_verification()
        user = _make_user(status="pending_verification")

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(verification)
            elif call_count == 2:
                return _mock_scalar_result(user)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await svc.verify_email("token")
        assert result is user
        assert user.email_verified_at is not None
        assert user.status == "active"


class TestAuthServiceLogin:
    @pytest.mark.asyncio
    async def test_login_user_not_found(self):
        from app.services.auth import AuthService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = AuthService(db)
        db.execute = AsyncMock(return_value=_mock_scalar_result(None))

        with pytest.raises(ApiError) as exc_info:
            await svc.login("nonexistent@example.com", "password1234!")
        assert exc_info.value.code == "INVALID_CREDENTIALS"

    @pytest.mark.asyncio
    async def test_login_wrong_password(self):
        from app.services.auth import AuthService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = AuthService(db)
        user = _make_user()

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(user)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with (
            patch("app.services.auth.verify_password", return_value=False),
            patch("app.services.auth.get_settings") as mock_settings,
        ):
            mock_settings.return_value = MagicMock(app_env="development")
            with pytest.raises(ApiError) as exc_info:
                await svc.login("test@example.com", "wrongpassword!")
            assert exc_info.value.code == "INVALID_CREDENTIALS"

    @pytest.mark.asyncio
    async def test_login_account_locked(self):
        from app.services.auth import AuthService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = AuthService(db)
        user = _make_user(status="locked", locked_until=datetime.now(UTC) + timedelta(minutes=10))

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(user)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with (
            patch("app.services.auth.verify_password", return_value=True),
            patch("app.services.auth.get_settings") as mock_settings,
        ):
            mock_settings.return_value = MagicMock(app_env="development")
            with pytest.raises(ApiError) as exc_info:
                await svc.login("test@example.com", "SecureP@ss123!")
            assert exc_info.value.code == "ACCOUNT_LOCKED"

    @pytest.mark.asyncio
    async def test_login_disabled_account(self):
        from app.services.auth import AuthService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = AuthService(db)
        user = _make_user(status="disabled")

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(user)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with (
            patch("app.services.auth.verify_password", return_value=True),
            patch("app.services.auth.get_settings") as mock_settings,
        ):
            mock_settings.return_value = MagicMock(app_env="development")
            with pytest.raises(ApiError) as exc_info:
                await svc.login("test@example.com", "SecureP@ss123!")
            assert exc_info.value.code == "ACCOUNT_DISABLED"

    @pytest.mark.asyncio
    async def test_login_deleted_account(self):
        from app.services.auth import AuthService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = AuthService(db)
        user = _make_user(status="deleted")

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(user)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with (
            patch("app.services.auth.verify_password", return_value=True),
            patch("app.services.auth.get_settings") as mock_settings,
        ):
            mock_settings.return_value = MagicMock(app_env="development")
            with pytest.raises(ApiError) as exc_info:
                await svc.login("test@example.com", "SecureP@ss123!")
            assert exc_info.value.code == "INVALID_CREDENTIALS"

    @pytest.mark.asyncio
    async def test_login_happy_path(self):
        from app.services.auth import AuthService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = AuthService(db)
        user = _make_user()

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(user)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with (
            patch("app.services.auth.verify_password", return_value=True),
            patch("app.services.auth.needs_rehash", return_value=False),
            patch("app.services.auth.get_settings") as mock_settings,
            patch("app.services.auth.create_access_token", return_value="access-token"),
            patch("app.services.auth.generate_csrf_token", return_value="csrf-token"),
            patch("app.services.auth.generate_jti", return_value="jti-1"),
            patch("app.services.auth.generate_token", return_value="refresh-token"),
            patch("app.services.auth.hash_token", return_value="hashed"),
        ):
            mock_settings.return_value = MagicMock(
                app_env="development",
                refresh_token_ttl_seconds=2592000,
                access_token_ttl_seconds=900,
            )
            result = await svc.login("test@example.com", "SecureP@ss123!")
            assert result["user"] is user
            assert result["access_token"] == "access-token"
            assert result["refresh_token"] == "refresh-token"
            assert result["csrf_token"] == "csrf-token"

    @pytest.mark.asyncio
    async def test_login_lock_expired_unlocks(self):
        from app.services.auth import AuthService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = AuthService(db)
        user = _make_user(status="locked", locked_until=datetime.now(UTC) - timedelta(minutes=1))

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(user)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with (
            patch("app.services.auth.verify_password", return_value=True),
            patch("app.services.auth.needs_rehash", return_value=False),
            patch("app.services.auth.get_settings") as mock_settings,
            patch("app.services.auth.create_access_token", return_value="at"),
            patch("app.services.auth.generate_csrf_token", return_value="csrf"),
            patch("app.services.auth.generate_jti", return_value="jti"),
            patch("app.services.auth.generate_token", return_value="rt"),
            patch("app.services.auth.hash_token", return_value="hashed"),
        ):
            mock_settings.return_value = MagicMock(app_env="development", refresh_token_ttl_seconds=86400)
            await svc.login("test@example.com", "SecureP@ss123!")
            assert user.status == "active"
            assert user.failed_login_count == 0


class TestAuthServiceRefresh:
    @pytest.mark.asyncio
    async def test_refresh_invalid_token(self):
        from app.services.auth import AuthService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = AuthService(db)
        db.execute = AsyncMock(return_value=_mock_scalar_result(None))

        with pytest.raises(ApiError) as exc_info:
            await svc.refresh("invalid-refresh-token")
        assert exc_info.value.code == "INVALID_TOKEN"

    @pytest.mark.asyncio
    async def test_refresh_expired_token(self):
        from app.services.auth import AuthService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = AuthService(db)
        token = _make_refresh_token(expires_at=datetime.now(UTC) - timedelta(hours=1))
        db.execute = AsyncMock(return_value=_mock_scalar_result(token))

        with pytest.raises(ApiError) as exc_info:
            await svc.refresh("expired-token")
        assert exc_info.value.code == "TOKEN_EXPIRED"

    @pytest.mark.asyncio
    async def test_refresh_reuse_detected(self):
        from app.services.auth import AuthService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = AuthService(db)
        token = _make_refresh_token(used_at=datetime.now(UTC))  # already used

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(token)
            return MagicMock()

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with pytest.raises(ApiError) as exc_info:
            await svc.refresh("reused-token")
        assert exc_info.value.code == "REFRESH_TOKEN_REUSE"

    @pytest.mark.asyncio
    async def test_refresh_happy_path(self):
        from app.services.auth import AuthService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = AuthService(db)
        token = _make_refresh_token()
        session = _make_session()

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # find refresh token
                return _mock_scalar_result(token)
            elif call_count == 2:  # find session
                return _mock_scalar_result(session)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with (
            patch("app.services.auth.get_settings") as mock_settings,
            patch("app.services.auth.create_access_token", return_value="new-access"),
            patch("app.services.auth.generate_csrf_token", return_value="new-csrf"),
            patch("app.services.auth.generate_jti", return_value="new-jti"),
            patch("app.services.auth.generate_token", return_value="new-refresh"),
            patch("app.services.auth.hash_token", return_value="new-hash"),
        ):
            mock_settings.return_value = MagicMock(refresh_token_ttl_seconds=2592000)
            result = await svc.refresh("valid-refresh-token")
            assert result["access_token"] == "new-access"
            assert result["refresh_token"] == "new-refresh"
            assert result["csrf_token"] == "new-csrf"


class TestAuthServiceLogout:
    @pytest.mark.asyncio
    async def test_logout_session_found(self):
        from app.services.auth import AuthService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = AuthService(db)
        session = _make_session()
        db.execute = AsyncMock(return_value=_mock_scalar_result(session))

        await svc.logout("sess-1", "user-1")
        assert session.revoked_at is not None
        assert session.revoke_reason == "logout"
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_logout_session_not_found(self):
        from app.services.auth import AuthService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = AuthService(db)
        db.execute = AsyncMock(return_value=_mock_scalar_result(None))

        # Should not raise when session not found
        await svc.logout("sess-1", "user-1")
        db.commit.assert_not_awaited()


class TestAuthServiceLogoutAll:
    @pytest.mark.asyncio
    async def test_logout_all_with_sessions(self):
        from app.services.auth import AuthService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = AuthService(db)

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # session IDs
                mock = MagicMock()
                mock.all.return_value = [("sess-1",), ("sess-2",)]
                return mock
            return MagicMock()

        db.execute = AsyncMock(side_effect=execute_side_effect)

        await svc.logout_all("user-1")
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_logout_all_no_sessions(self):
        from app.services.auth import AuthService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = AuthService(db)

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                mock = MagicMock()
                mock.all.return_value = []
                return mock
            return MagicMock()

        db.execute = AsyncMock(side_effect=execute_side_effect)

        await svc.logout_all("user-1")
        db.commit.assert_awaited()
