"""Worker tests for outbox publisher and task runtime."""

from __future__ import annotations

from app.models.outbox import OutboxEvent


class TestOutboxEventModel:
    """Test OutboxEvent ORM model."""

    def test_outbox_event_table_name(self) -> None:
        """OutboxEvent should use outbox_events table."""
        assert OutboxEvent.__tablename__ == "outbox_events"

    def test_outbox_event_has_required_columns(self) -> None:
        """OutboxEvent should have all required columns."""
        columns = {c.name for c in OutboxEvent.__table__.columns}
        required = {
            "id",
            "event_type",
            "aggregate_type",
            "aggregate_id",
            "payload",
            "status",
            "attempt_count",
            "max_attempts",
            "available_at",
            "last_error",
            "created_at",
            "published_at",
        }
        assert required.issubset(columns)


class TestTaskStatusTransition:
    """Test task status transition logic."""

    def test_valid_transitions(self) -> None:
        """Test valid task status transitions."""
        from app.models.task import validate_task_transition

        assert validate_task_transition("pending", "running") is True
        assert validate_task_transition("running", "completed") is True
        assert validate_task_transition("running", "failed") is True
        assert validate_task_transition("running", "cancel_requested") is True
        assert validate_task_transition("pending", "cancelled") is True

    def test_invalid_transitions(self) -> None:
        """Test invalid task status transitions."""
        from app.models.task import validate_task_transition

        assert validate_task_transition("completed", "running") is False
        assert validate_task_transition("failed", "running") is False
        assert validate_task_transition("cancelled", "running") is False


class TestGoalStateTransition:
    """Test goal state transition logic."""

    def test_valid_goal_transitions(self) -> None:
        """Test valid goal status transitions."""
        from app.models.goal import validate_goal_transition

        assert validate_goal_transition("draft", "clarifying") is True
        assert validate_goal_transition("clarifying", "diagnosing") is True
        assert validate_goal_transition("diagnosing", "planning") is True
        assert validate_goal_transition("planning", "ready") is True
        assert validate_goal_transition("ready", "active") is True

    def test_invalid_goal_transitions(self) -> None:
        """Test invalid goal status transitions."""
        from app.models.goal import validate_goal_transition

        assert validate_goal_transition("active", "draft") is False
        assert validate_goal_transition("completed", "draft") is False
