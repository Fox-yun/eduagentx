"""Tests for app/core/auth_deps.py — authentication dependency functions."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.common.datetime import utc_now
from app.core.auth_deps import (
    get_current_session,
    get_current_user,
    require_active_user,
    require_learning_user,
    require_verified_user,
)
from app.core.errors import ApiError


def _make_user(
    *,
    status: str = "active",
    email_verified_at: object = True,
    onboarding_completed_at: object = True,
) -> MagicMock:
    user = MagicMock()
    user.id = "user-1"
    user.status = status
    user.email_verified_at = utc_now() if email_verified_at is True else email_verified_at
    if onboarding_completed_at is True:
        user.onboarding_completed_at = utc_now()
    else:
        user.onboarding_completed_at = onboarding_completed_at
    return user


def _make_session(*, expired: bool = False) -> MagicMock:
    session = MagicMock()
    session.id = "session-1"
    session.user_id = "user-1"
    if expired:
        session.expires_at = utc_now() - timedelta(hours=1)
    else:
        session.expires_at = utc_now() + timedelta(hours=1)
    return session


class TestGetCurrentSession:
    @pytest.mark.asyncio
    async def test_no_token_raises_401(self):
        with pytest.raises(ApiError) as exc:
            await get_current_session(
                request=MagicMock(),
                access_token=None,
                db=AsyncMock(),
            )
        assert exc.value.status_code == 401
        assert exc.value.code == "UNAUTHENTICATED"

    @pytest.mark.asyncio
    async def test_valid_token_returns_session_info(self):
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_session = _make_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute = AsyncMock(return_value=mock_result)

        with (
            patch("app.core.auth_deps.decode_access_token", return_value={"sub": "user-1", "sid": "session-1"}),
            patch("app.core.auth_deps.utc_now", return_value=utc_now()),
        ):
            result = await get_current_session(
                request=MagicMock(),
                access_token="valid.jwt.token",
                db=mock_db,
            )

        assert result == {"user_id": "user-1", "session_id": "session-1"}

    @pytest.mark.asyncio
    async def test_token_without_sub_raises(self):
        with patch("app.core.auth_deps.decode_access_token", return_value={"sid": "session-1"}):
            with pytest.raises(ApiError) as exc:
                await get_current_session(
                    request=MagicMock(),
                    access_token="token",
                    db=AsyncMock(),
                )
            assert exc.value.code == "INVALID_TOKEN"

    @pytest.mark.asyncio
    async def test_revoked_session_raises(self):
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.core.auth_deps.decode_access_token", return_value={"sub": "u1", "sid": "s1"}):
            with pytest.raises(ApiError) as exc:
                await get_current_session(
                    request=MagicMock(),
                    access_token="token",
                    db=mock_db,
                )
            assert exc.value.code == "SESSION_REVOKED"

    @pytest.mark.asyncio
    async def test_expired_session_raises(self):
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_session = _make_session(expired=True)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.core.auth_deps.decode_access_token", return_value={"sub": "u1", "sid": "s1"}):
            with pytest.raises(ApiError) as exc:
                await get_current_session(
                    request=MagicMock(),
                    access_token="token",
                    db=mock_db,
                )
            assert exc.value.code == "SESSION_EXPIRED"


class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_valid_user(self):
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_user = _make_user()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute = AsyncMock(return_value=mock_result)

        user = await get_current_user(session={"user_id": "user-1"}, db=mock_db)
        assert user == mock_user

    @pytest.mark.asyncio
    async def test_user_not_found_raises(self):
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ApiError) as exc:
            await get_current_user(session={"user_id": "u1"}, db=mock_db)
        assert exc.value.code == "USER_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_deleted_user_raises(self):
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_user = _make_user(status="deleted")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ApiError) as exc:
            await get_current_user(session={"user_id": "u1"}, db=mock_db)
        assert exc.value.code == "USER_NOT_FOUND"


class TestRequireVerifiedUser:
    @pytest.mark.asyncio
    async def test_verified_user_passes(self):
        user = _make_user(email_verified_at=True)
        result = await require_verified_user(user=user)
        assert result == user

    @pytest.mark.asyncio
    async def test_unverified_user_raises(self):
        user = _make_user(email_verified_at=None)
        with pytest.raises(ApiError) as exc:
            await require_verified_user(user=user)
        assert exc.value.code == "EMAIL_NOT_VERIFIED"


class TestRequireActiveUser:
    @pytest.mark.asyncio
    async def test_active_user_passes(self):
        user = _make_user(status="active")
        result = await require_active_user(user=user)
        assert result == user

    @pytest.mark.asyncio
    async def test_locked_user_raises(self):
        user = _make_user(status="locked")
        with pytest.raises(ApiError) as exc:
            await require_active_user(user=user)
        assert exc.value.code == "ACCOUNT_LOCKED"

    @pytest.mark.asyncio
    async def test_disabled_user_raises(self):
        user = _make_user(status="disabled")
        with pytest.raises(ApiError) as exc:
            await require_active_user(user=user)
        assert exc.value.code == "ACCOUNT_DISABLED"


class TestRequireLearningUser:
    @pytest.mark.asyncio
    async def test_onboarded_user_passes(self):
        user = _make_user(onboarding_completed_at=True)
        result = await require_learning_user(user=user)
        assert result == user

    @pytest.mark.asyncio
    async def test_no_onboarding_raises(self):
        user = _make_user(onboarding_completed_at=None)
        with pytest.raises(ApiError) as exc:
            await require_learning_user(user=user)
        assert exc.value.code == "ONBOARDING_REQUIRED"
