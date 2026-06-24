"""Tests for goal state machine."""

from __future__ import annotations

from app.models.goal import GOAL_STATE_TRANSITIONS, validate_goal_transition


class TestGoalStateTransitions:
    def test_draft_to_clarifying(self):
        assert validate_goal_transition("draft", "clarifying")

    def test_draft_to_diagnosing(self):
        assert validate_goal_transition("draft", "diagnosing")

    def test_draft_to_planning(self):
        assert validate_goal_transition("draft", "planning")

    def test_clarifying_to_diagnosing(self):
        assert validate_goal_transition("clarifying", "diagnosing")

    def test_planning_to_ready(self):
        assert validate_goal_transition("planning", "ready")

    def test_ready_to_active(self):
        assert validate_goal_transition("ready", "active")

    def test_active_to_completed(self):
        assert validate_goal_transition("active", "completed")

    def test_completed_to_archived(self):
        assert validate_goal_transition("completed", "archived")

    def test_failed_to_draft(self):
        assert validate_goal_transition("failed", "draft")

    def test_invalid_transition_draft_to_active(self):
        assert not validate_goal_transition("draft", "active")

    def test_invalid_transition_active_to_draft(self):
        assert not validate_goal_transition("active", "draft")

    def test_invalid_transition_archived_to_any(self):
        for target in GOAL_STATE_TRANSITIONS:
            assert not validate_goal_transition("archived", target)

    def test_all_states_have_transitions(self):
        """Every non-terminal state should have at least one valid transition."""
        for state, transitions in GOAL_STATE_TRANSITIONS.items():
            if state != "archived":
                assert len(transitions) > 0, f"State '{state}' has no valid transitions"
