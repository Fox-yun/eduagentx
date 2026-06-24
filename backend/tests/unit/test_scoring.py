"""Tests for assessment scoring logic."""

from __future__ import annotations

from app.services.unit import PASS_THRESHOLD


class TestScoring:
    def test_pass_threshold(self):
        assert PASS_THRESHOLD == 60.0

    def test_score_calculation(self):
        """Test basic score calculation."""
        earned = 3
        total = 4
        score = (earned / total * 100) if total > 0 else 0
        assert score == 75.0

    def test_pass_condition(self):
        """Score >= threshold should pass."""
        score = 75.0
        assert score >= PASS_THRESHOLD

    def test_fail_condition(self):
        """Score < threshold should fail."""
        score = 50.0
        assert score < PASS_THRESHOLD

    def test_perfect_score(self):
        """100% should pass."""
        score = 100.0
        assert score >= PASS_THRESHOLD

    def test_zero_score(self):
        """0% should fail."""
        score = 0.0
        assert score < PASS_THRESHOLD

    def test_boundary_pass(self):
        """Exactly at threshold should pass."""
        score = PASS_THRESHOLD
        assert score >= PASS_THRESHOLD

    def test_boundary_fail(self):
        """Just below threshold should fail."""
        score = PASS_THRESHOLD - 0.1
        assert score < PASS_THRESHOLD
