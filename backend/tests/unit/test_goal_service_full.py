"""Comprehensive unit tests for GoalService."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors import ApiError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_goal(**overrides):
    g = MagicMock()
    g.id = overrides.get("id", "goal-1")
    g.user_id = overrides.get("user_id", "user-1")
    g.title = overrides.get("title", "Learn Python")
    g.raw_description = overrides.get("raw_description", "Learn Python from scratch")
    g.status = overrides.get("status", "draft")
    g.current_level = overrides.get("current_level")
    g.target_level = overrides.get("target_level")
    g.weekly_hours = overrides.get("weekly_hours", 10)
    g.preferences = overrides.get("preferences", '["video"]')
    g.use_diagnostic = overrides.get("use_diagnostic", True)
    g.use_knowledge_base = overrides.get("use_knowledge_base", False)
    g.content_language = overrides.get("content_language", "zh")
    g.active_task_id = overrides.get("active_task_id")
    g.current_path_id = overrides.get("current_path_id")
    g.created_at = overrides.get("created_at", datetime.now(UTC))
    g.updated_at = overrides.get("updated_at", datetime.now(UTC))
    return g


def _mock_scalar_result(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _mock_scalars(items):
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


def _mock_scalar(value):
    r = MagicMock()
    r.scalar.return_value = value
    return r


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGoalServiceCreateGoal:
    @pytest.mark.asyncio
    async def test_create_goal_happy_path(self):
        from app.services.goal import GoalService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = GoalService(db)

        result = await svc.create_goal(user_id="user-1", raw_goal="Learn Python")
        assert "goal" in result
        assert result["next_step"] == "clarify"  # use_diagnostic=True
        db.add.assert_called()
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_create_goal_no_diagnostic(self):
        from app.services.goal import GoalService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = GoalService(db)

        result = await svc.create_goal(
            user_id="user-1",
            raw_goal="Learn Python",
            use_diagnostic=False,
        )
        assert result["next_step"] == "generating"

    @pytest.mark.asyncio
    async def test_create_goal_with_all_params(self):
        from app.services.goal import GoalService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = GoalService(db)

        result = await svc.create_goal(
            user_id="user-1",
            raw_goal="Learn machine learning",
            current_level="intermediate",
            target_level="advanced",
            duration_weeks=12,
            weekly_hours=15,
            preferences=["video", "practice"],
            use_diagnostic=True,
            use_knowledge_base=True,
            content_language="en",
        )
        goal = result["goal"]
        assert goal.current_level == "intermediate"
        assert goal.target_level == "advanced"
        assert goal.weekly_hours == 15

    @pytest.mark.asyncio
    async def test_create_goal_title_truncated(self):
        from app.services.goal import GoalService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = GoalService(db)

        long_title = "x" * 1000
        result = await svc.create_goal(user_id="user-1", raw_goal=long_title)
        assert len(result["goal"].title) == 500


class TestGoalServiceGetGoal:
    @pytest.mark.asyncio
    async def test_get_goal_found(self):
        from app.services.goal import GoalService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = GoalService(db)
        goal = _make_goal()
        db.execute = AsyncMock(return_value=_mock_scalar_result(goal))

        result = await svc.get_goal("goal-1", "user-1")
        assert result is goal

    @pytest.mark.asyncio
    async def test_get_goal_not_found(self):
        from app.services.goal import GoalService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = GoalService(db)
        db.execute = AsyncMock(return_value=_mock_scalar_result(None))

        with pytest.raises(ApiError) as exc_info:
            await svc.get_goal("nonexistent", "user-1")
        assert exc_info.value.code == "GOAL_NOT_FOUND"
        assert exc_info.value.status_code == 404


class TestGoalServiceListGoals:
    @pytest.mark.asyncio
    async def test_list_goals_no_cursor(self):
        from app.services.goal import GoalService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = GoalService(db)
        goals = [_make_goal(id=f"g{i}") for i in range(3)]

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # count
                return _mock_scalar(3)
            elif call_count == 2:  # items
                return _mock_scalars(goals)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await svc.list_goals("user-1")
        assert len(result["items"]) == 3
        assert result["next_cursor"] is None
        assert result["total"] == 3

    @pytest.mark.asyncio
    async def test_list_goals_with_next_page(self):
        from app.services.goal import GoalService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = GoalService(db)
        # Return limit+1 items to trigger has_next
        goals = [_make_goal(id=f"g{i}", created_at=datetime.now(UTC)) for i in range(21)]

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar(25)
            elif call_count == 2:
                return _mock_scalars(goals)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await svc.list_goals("user-1", limit=20)
        assert len(result["items"]) == 20
        assert result["next_cursor"] is not None

    @pytest.mark.asyncio
    async def test_list_goals_invalid_limit(self):
        from app.services.goal import GoalService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = GoalService(db)

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar(0)
            elif call_count == 2:
                return _mock_scalars([])
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await svc.list_goals("user-1", limit=0)  # invalid, should default to 20
        assert result["items"] == []

    @pytest.mark.asyncio
    async def test_list_goals_empty(self):
        from app.services.goal import GoalService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = GoalService(db)

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar(0)
            elif call_count == 2:
                return _mock_scalars([])
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await svc.list_goals("user-1")
        assert result["items"] == []
        assert result["total"] == 0


class TestGoalServiceUpdateGoal:
    @pytest.mark.asyncio
    async def test_update_goal_happy_path(self):
        from app.services.goal import GoalService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = GoalService(db)
        goal = _make_goal()
        db.execute = AsyncMock(return_value=_mock_scalar_result(goal))

        result = await svc.update_goal("goal-1", "user-1", title="New Title")
        assert result is goal
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_update_goal_none_values_skipped(self):
        from app.services.goal import GoalService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = GoalService(db)
        goal = _make_goal(title="Original")
        db.execute = AsyncMock(return_value=_mock_scalar_result(goal))

        await svc.update_goal("goal-1", "user-1", title=None, current_level="advanced")
        # title should remain "Original" since None was passed
        assert goal.title == "Original"
        assert goal.current_level == "advanced"

    @pytest.mark.asyncio
    async def test_update_goal_not_found(self):
        from app.services.goal import GoalService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = GoalService(db)
        db.execute = AsyncMock(return_value=_mock_scalar_result(None))

        with pytest.raises(ApiError):
            await svc.update_goal("nonexistent", "user-1", title="New")


class TestGoalServiceTransitionGoal:
    @pytest.mark.asyncio
    async def test_transition_valid(self):
        from app.services.goal import GoalService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = GoalService(db)
        goal = _make_goal(status="draft")
        db.execute = AsyncMock(return_value=_mock_scalar_result(goal))

        result = await svc.transition_goal("goal-1", "user-1", "clarifying")
        assert result.status == "clarifying"

    @pytest.mark.asyncio
    async def test_transition_with_task_id(self):
        from app.services.goal import GoalService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = GoalService(db)
        goal = _make_goal(status="draft")
        db.execute = AsyncMock(return_value=_mock_scalar_result(goal))

        result = await svc.transition_goal("goal-1", "user-1", "planning", task_id="task-1")
        assert result.active_task_id == "task-1"

    @pytest.mark.asyncio
    async def test_transition_invalid(self):
        from app.services.goal import GoalService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = GoalService(db)
        goal = _make_goal(status="draft")
        db.execute = AsyncMock(return_value=_mock_scalar_result(goal))

        with pytest.raises(ApiError) as exc_info:
            await svc.transition_goal("goal-1", "user-1", "active")  # draft -> active is invalid
        assert exc_info.value.code == "INVALID_TRANSITION"

    @pytest.mark.asyncio
    async def test_transition_from_planning_to_ready(self):
        from app.services.goal import GoalService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = GoalService(db)
        goal = _make_goal(status="planning")
        db.execute = AsyncMock(return_value=_mock_scalar_result(goal))

        result = await svc.transition_goal("goal-1", "user-1", "ready")
        assert result.status == "ready"


class TestGoalServiceDeleteGoal:
    @pytest.mark.asyncio
    async def test_delete_goal_archives(self):
        from app.services.goal import GoalService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = GoalService(db)
        goal = _make_goal(status="active")
        db.execute = AsyncMock(return_value=_mock_scalar_result(goal))

        await svc.delete_goal("goal-1", "user-1")
        assert goal.status == "archived"
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_delete_goal_not_found(self):
        from app.services.goal import GoalService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = GoalService(db)
        db.execute = AsyncMock(return_value=_mock_scalar_result(None))

        with pytest.raises(ApiError):
            await svc.delete_goal("nonexistent", "user-1")
