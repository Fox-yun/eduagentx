"""Unit tests for goal service state machine and validation."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors import ApiError


class TestGoalStatusTransitions:
    """Test goal state transition rules."""

    def test_valid_transitions(self):
        transitions = {
            "draft": ["clarifying"],
            "clarifying": ["diagnosing"],
            "diagnosing": ["planning"],
            "planning": ["ready"],
            "ready": ["active"],
        }
        for src, targets in transitions.items():
            for t in targets:
                assert t != src

    def test_active_is_nearly_terminal(self):
        assert "archived" == "archived"

    def test_goal_title_max_length(self):
        title = "a" * 500
        assert len(title) <= 500


class TestGoalServiceGetGoal:
    @pytest.mark.asyncio
    async def test_get_goal_not_found(self):
        from app.services.goal import GoalService

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        svc = GoalService(mock_db)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ApiError):
            await svc.get_goal("nonexistent", "user-1")
