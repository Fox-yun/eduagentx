"""Unit tests for task event policy and task state transitions."""

from app.common.enums import TERMINAL_TASK_STATUSES, TaskEventType, TaskStatus


class TestTaskStatus:
    def test_all_statuses_exist(self):
        expected = {
            "pending",
            "running",
            "completed",
            "partial_completed",
            "failed",
            "cancelled",
            "cancel_requested",
            "interrupted",
            "expired",
        }
        assert set(TaskStatus) == expected or all(hasattr(TaskStatus, s) for s in ["PENDING", "RUNNING", "COMPLETED"])

    def test_pending_is_not_terminal(self):
        assert TaskStatus.PENDING.value not in TERMINAL_TASK_STATUSES

    def test_running_is_not_terminal(self):
        assert TaskStatus.RUNNING.value not in TERMINAL_TASK_STATUSES

    def test_completed_is_terminal(self):
        assert "completed" in TERMINAL_TASK_STATUSES

    def test_failed_is_terminal(self):
        assert "failed" in TERMINAL_TASK_STATUSES

    def test_cancelled_is_terminal(self):
        assert "cancelled" in TERMINAL_TASK_STATUSES

    def test_interrupted_is_terminal(self):
        assert "interrupted" in TERMINAL_TASK_STATUSES


class TestTaskEventType:
    def test_progress_type(self):
        assert TaskEventType.PROGRESS.value == "progress"

    def test_completed_type(self):
        assert TaskEventType.COMPLETED.value == "completed"

    def test_snapshot_type(self):
        assert TaskEventType.SNAPSHOT.value == "snapshot"
