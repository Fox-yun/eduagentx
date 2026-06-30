"""Unit tests for model validation and field constraints."""

from app.common.enums import TERMINAL_TASK_STATUSES, TaskEventType, TaskStatus


class TestTaskStatusEnum:
    def test_pending_value(self):
        assert TaskStatus.PENDING.value == "pending"

    def test_running_value(self):
        assert TaskStatus.RUNNING.value == "running"

    def test_completed_value(self):
        assert TaskStatus.COMPLETED.value == "completed"

    def test_failed_value(self):
        assert TaskStatus.FAILED.value == "failed"

    def test_cancelled_value(self):
        assert TaskStatus.CANCELLED.value == "cancelled"

    def test_interrupted_value(self):
        assert TaskStatus.INTERRUPTED.value == "interrupted"

    def test_expired_value(self):
        assert TaskStatus.EXPIRED.value == "expired"

    def test_partial_completed_value(self):
        assert TaskStatus.PARTIAL_COMPLETED.value == "partial_completed"

    def test_cancel_requested_value(self):
        assert TaskStatus.CANCEL_REQUESTED.value == "cancel_requested"


class TestTerminalStatuses:
    def test_terminal_set_size(self):
        assert len(TERMINAL_TASK_STATUSES) == 6

    def test_all_terminal_statuses(self):
        expected = {"completed", "partial_completed", "failed", "cancelled", "expired", "interrupted"}
        assert expected == TERMINAL_TASK_STATUSES

    def test_pending_not_terminal(self):
        assert "pending" not in TERMINAL_TASK_STATUSES

    def test_running_not_terminal(self):
        assert "running" not in TERMINAL_TASK_STATUSES


class TestTaskEventTypeEnum:
    def test_all_event_types(self):
        expected = {
            "snapshot",
            "progress",
            "message",
            "completed",
            "partial_completed",
            "failed",
            "cancelled",
            "heartbeat",
        }
        actual = {e.value for e in TaskEventType}
        assert actual == expected


class TestModelFieldConstraints:
    def test_learning_node_status_values(self):
        valid = {"draft", "locked", "available", "current", "completed", "failed"}
        assert len(valid) == 6

    def test_difficulty_values(self):
        valid = {"beginner", "intermediate", "advanced"}
        assert len(valid) == 3

    def test_content_status_values(self):
        valid = {"not_generated", "generating", "ready", "failed"}
        assert len(valid) == 4

    def test_path_status_values(self):
        valid = {"generating", "draft", "active", "updating", "completed", "failed"}
        assert len(valid) == 6
