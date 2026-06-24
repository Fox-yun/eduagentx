"""Tests for task state machine."""

from __future__ import annotations

from app.common.enums import TERMINAL_TASK_STATUSES, TaskStatus
from app.models.task import TASK_STATE_TRANSITIONS, validate_task_transition


class TestTaskStateTransitions:
    def test_pending_to_running(self):
        assert validate_task_transition(TaskStatus.PENDING.value, TaskStatus.RUNNING.value)

    def test_pending_to_cancelled(self):
        assert validate_task_transition(TaskStatus.PENDING.value, TaskStatus.CANCELLED.value)

    def test_running_to_completed(self):
        assert validate_task_transition(TaskStatus.RUNNING.value, TaskStatus.COMPLETED.value)

    def test_running_to_failed(self):
        assert validate_task_transition(TaskStatus.RUNNING.value, TaskStatus.FAILED.value)

    def test_running_to_cancel_requested(self):
        assert validate_task_transition(TaskStatus.RUNNING.value, TaskStatus.CANCEL_REQUESTED.value)

    def test_cancel_requested_to_cancelled(self):
        assert validate_task_transition(TaskStatus.CANCEL_REQUESTED.value, TaskStatus.CANCELLED.value)

    def test_failed_to_pending(self):
        assert validate_task_transition(TaskStatus.FAILED.value, TaskStatus.PENDING.value)

    def test_interrupted_to_pending(self):
        assert validate_task_transition(TaskStatus.INTERRUPTED.value, TaskStatus.PENDING.value)

    def test_invalid_completed_to_running(self):
        assert not validate_task_transition(TaskStatus.COMPLETED.value, TaskStatus.RUNNING.value)

    def test_invalid_cancelled_to_running(self):
        assert not validate_task_transition(TaskStatus.CANCELLED.value, TaskStatus.RUNNING.value)

    def test_terminal_states_have_no_transitions(self):
        """Terminal states should have no valid transitions (except failed/interrupted for retry)."""
        for status in TERMINAL_TASK_STATUSES:
            transitions = TASK_STATE_TRANSITIONS.get(status, set())
            if status in (TaskStatus.FAILED.value, TaskStatus.INTERRUPTED.value):
                assert len(transitions) > 0, f"State '{status}' should allow retry"
            else:
                assert len(transitions) == 0, f"Terminal state '{status}' should have no transitions"

    def test_all_states_defined(self):
        """All task states should have transition definitions."""
        for status in TaskStatus:
            assert status.value in TASK_STATE_TRANSITIONS, f"Missing transitions for '{status.value}'"
