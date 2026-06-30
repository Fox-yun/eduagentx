"""Comprehensive unit tests for UserService."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

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
    u.display_name = overrides.get("display_name", "Test User")
    u.email_verified_at = overrides.get("email_verified_at", datetime.now(UTC))
    u.onboarding_completed_at = overrides.get("onboarding_completed_at")
    u.status = overrides.get("status", "active")
    return u


def _make_profile(**overrides):
    p = MagicMock()
    p.user_id = overrides.get("user_id", "user-1")
    p.role = overrides.get("role", "student")
    p.preferred_language = overrides.get("preferred_language", "zh")
    p.timezone = overrides.get("timezone", "Asia/Shanghai")
    p.weekly_hours = overrides.get("weekly_hours", 10)
    p.learning_interests = overrides.get("learning_interests", '["python"]')
    p.learning_preferences = overrides.get("learning_preferences", '["video"]')
    p.use_diagnostic = overrides.get("use_diagnostic", True)
    p.use_knowledge_base = overrides.get("use_knowledge_base", False)
    return p


class TestUserServiceGetProfile:
    @pytest.mark.asyncio
    async def test_get_profile_happy_path(self):
        from app.services.user import UserService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = UserService(db)
        user = _make_user()
        profile = _make_profile()

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # profile
                return _mock_scalar_result(profile)
            elif call_count == 2:  # user
                return _mock_scalar_result(user)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await svc.get_profile("user-1")
        assert result["user_id"] == "user-1"
        assert result["email"] == "test@example.com"
        assert result["display_name"] == "Test User"
        assert result["email_verified"] is True
        assert result["onboarding_completed"] is False
        assert result["profile"]["role"] == "student"
        assert result["profile"]["learning_interests"] == ["python"]

    @pytest.mark.asyncio
    async def test_get_profile_not_found(self):
        from app.services.user import UserService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = UserService(db)
        db.execute = AsyncMock(return_value=_mock_scalar_result(None))

        with pytest.raises(ApiError) as exc_info:
            await svc.get_profile("user-1")
        assert exc_info.value.code == "PROFILE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_get_profile_user_not_found(self):
        from app.services.user import UserService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = UserService(db)
        profile = _make_profile()

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(profile)
            elif call_count == 2:
                return _mock_scalar_result(None)  # user not found
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with pytest.raises(ApiError) as exc_info:
            await svc.get_profile("user-1")
        assert exc_info.value.code == "USER_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_get_profile_with_onboarding(self):
        from app.services.user import UserService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = UserService(db)
        user = _make_user(onboarding_completed_at=datetime.now(UTC))
        profile = _make_profile()

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(profile)
            elif call_count == 2:
                return _mock_scalar_result(user)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await svc.get_profile("user-1")
        assert result["onboarding_completed"] is True

    @pytest.mark.asyncio
    async def test_get_profile_no_email_verified(self):
        from app.services.user import UserService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = UserService(db)
        user = _make_user(email_verified_at=None)
        profile = _make_profile()

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(profile)
            elif call_count == 2:
                return _mock_scalar_result(user)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await svc.get_profile("user-1")
        assert result["email_verified"] is False


class TestUserServiceUpdateProfile:
    @pytest.mark.asyncio
    async def test_update_display_name(self):
        from app.services.user import UserService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = UserService(db)
        user = _make_user(display_name="Old Name")
        profile = _make_profile()

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(profile)
            elif call_count == 2:
                return _mock_scalar_result(user)
            elif call_count == 3:  # get_profile recursive call
                return _mock_scalar_result(profile)
            elif call_count == 4:
                return _mock_scalar_result(user)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        await svc.update_profile("user-1", display_name="  New Name  ")
        assert user.display_name == "New Name"
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_update_language_and_timezone(self):
        from app.services.user import UserService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = UserService(db)
        user = _make_user()
        profile = _make_profile()

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(profile)
            elif call_count == 2:
                return _mock_scalar_result(user)
            elif call_count == 3:
                return _mock_scalar_result(profile)
            elif call_count == 4:
                return _mock_scalar_result(user)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        await svc.update_profile("user-1", preferred_language="en", timezone="US/Eastern")
        assert profile.preferred_language == "en"
        assert profile.timezone == "US/Eastern"

    @pytest.mark.asyncio
    async def test_update_profile_not_found(self):
        from app.services.user import UserService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = UserService(db)
        db.execute = AsyncMock(return_value=_mock_scalar_result(None))

        with pytest.raises(ApiError):
            await svc.update_profile("user-1", display_name="New")


class TestUserServiceCompleteOnboarding:
    @pytest.mark.asyncio
    async def test_complete_onboarding_happy_path(self):
        from app.services.user import UserService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = UserService(db)
        user = _make_user(onboarding_completed_at=None)
        profile = _make_profile()

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(profile)
            elif call_count == 2:
                return _mock_scalar_result(user)
            elif call_count == 3:
                return _mock_scalar_result(profile)
            elif call_count == 4:
                return _mock_scalar_result(user)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        await svc.complete_onboarding(
            user_id="user-1",
            role="developer",
            learning_interests=["python", "ml"],
            learning_preferences=["video", "practice"],
            preferred_language="en",
            weekly_hours=20,
            use_diagnostic=False,
            use_knowledge_base=True,
        )
        assert profile.role == "developer"
        assert user.onboarding_completed_at is not None
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_complete_onboarding_profile_not_found(self):
        from app.services.user import UserService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = UserService(db)
        db.execute = AsyncMock(return_value=_mock_scalar_result(None))

        with pytest.raises(ApiError):
            await svc.complete_onboarding(
                user_id="user-1",
                role="student",
                learning_interests=["python"],
                learning_preferences=["video"],
            )

    @pytest.mark.asyncio
    async def test_complete_onboarding_user_not_found(self):
        from app.services.user import UserService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = UserService(db)
        profile = _make_profile()

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(profile)
            elif call_count == 2:
                return _mock_scalar_result(None)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with pytest.raises(ApiError):
            await svc.complete_onboarding(
                user_id="user-1",
                role="student",
                learning_interests=["python"],
                learning_preferences=["video"],
            )
