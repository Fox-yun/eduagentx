"""Unit tests for assessment finalization pure functions.

Tests _build_reentry_result, AssessmentFinalizationResult, and constants
without requiring a database.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.models.unit import AssessmentAttempt
from app.services.assessment_finalization import (
    ASSESSMENT_PASS_THRESHOLD,
    EVIDENCE_DIMENSIONS,
    MASTERY_ASSESSMENT_WEIGHT,
    MASTERY_HISTORY_WEIGHT,
    NODE_MASTERY_PASS_THRESHOLD,
    AssessmentFinalizationResult,
    _build_reentry_result,
)


class TestConstants:
    """Threshold and weight constants must not drift."""

    def test_assessment_pass_threshold(self):
        assert Decimal("60.00") == ASSESSMENT_PASS_THRESHOLD

    def test_node_mastery_threshold(self):
        assert Decimal("70.00") == NODE_MASTERY_PASS_THRESHOLD

    def test_weight_sum(self):
        assert Decimal("1.00") == MASTERY_HISTORY_WEIGHT + MASTERY_ASSESSMENT_WEIGHT

    def test_evidence_dimensions(self):
        assert len(EVIDENCE_DIMENSIONS) == 2
        dimensions = {d["dimension"] for d in EVIDENCE_DIMENSIONS}
        assert dimensions == {"concept_grasp", "knowledge_depth"}
        assert all(0 < d["confidence"] <= 1 for d in EVIDENCE_DIMENSIONS)


class TestAssessmentFinalizationResult:
    """Dataclass construction."""

    def test_minimal_construction(self):
        result = AssessmentFinalizationResult(
            attempt_id="a1",
            grading_quality="final",
            percentage=Decimal("65.00"),
            assessment_passed=True,
            node_completed=False,
            mastery_before=Decimal("0"),
            mastery_after=Decimal("65.00"),
            mastery_updated=True,
        )
        assert result.attempt_id == "a1"
        assert result.assessment_passed is True
        assert result.node_completed is False
        assert result.unlocked_node_ids == ()

    def test_passed_and_completed_both_true(self):
        result = AssessmentFinalizationResult(
            attempt_id="a2",
            grading_quality="final",
            percentage=Decimal("85.00"),
            assessment_passed=True,
            node_completed=True,
            mastery_before=Decimal("50.00"),
            mastery_after=Decimal("85.00"),
            mastery_updated=True,
            unlocked_node_ids=("n2", "n3"),
            profile_evidence_ids=("e1", "e2"),
        )
        assert result.assessment_passed is True
        assert result.node_completed is True
        assert len(result.unlocked_node_ids) == 2

    def test_frozen(self):
        result = AssessmentFinalizationResult(
            attempt_id="a3",
            grading_quality="provisional",
            percentage=Decimal("50.00"),
            assessment_passed=False,
            node_completed=False,
            mastery_before=Decimal("0"),
            mastery_after=Decimal("0"),
            mastery_updated=False,
        )
        with pytest.raises(AttributeError):
            result.percentage = Decimal("0")  # type: ignore[misc]


class TestBuildReentryResult:
    """Re-entry must return the same values persisted on the attempt."""

    def _make_attempt(self, **kwargs) -> MagicMock:
        defaults = dict(
            id="attempt-reentry",
            score=65.0,
            assessment_passed=True,
            node_completed=False,
            grading_quality="final",
            mastery_before=30.0,
            mastery_after=65.0,
            progress_applied_at=datetime.now(UTC),
        )
        defaults.update(kwargs)
        attempt = MagicMock(spec=AssessmentAttempt)
        for k, v in defaults.items():
            setattr(attempt, k, v)
        return attempt

    def test_passed_not_completed(self):
        """65% → assessment_passed=True but node_completed=False."""
        attempt = self._make_attempt(score=65.0, assessment_passed=True, node_completed=False)
        result = _build_reentry_result(attempt)
        assert result.percentage == Decimal("65.00")
        assert result.assessment_passed is True
        assert result.node_completed is False
        assert result.mastery_updated is True
        assert not result.unlocked_node_ids
        assert not result.profile_evidence_ids

    def test_both_passed_and_completed(self):
        attempt = self._make_attempt(score=85.0, assessment_passed=True, node_completed=True)
        result = _build_reentry_result(attempt)
        assert result.percentage == Decimal("85.00")
        assert result.assessment_passed is True
        assert result.node_completed is True
        assert result.mastery_updated is True

    def test_failed_assessment(self):
        attempt = self._make_attempt(score=40.0, assessment_passed=False, node_completed=False)
        result = _build_reentry_result(attempt)
        assert result.assessment_passed is False
        assert result.node_completed is False
        assert result.mastery_updated is True

    def test_provisional_reentry(self):
        attempt = self._make_attempt(
            score=50.0,
            assessment_passed=False,
            node_completed=False,
            grading_quality="provisional",
            progress_applied_at=None,
        )
        result = _build_reentry_result(attempt)
        assert result.grading_quality == "provisional"
        assert not result.mastery_updated  # provisional never updates progress

    def test_zero_score_does_not_error(self):
        attempt = self._make_attempt(score=0.0, assessment_passed=False, node_completed=False)
        result = _build_reentry_result(attempt)
        assert result.percentage == Decimal("0.00")
        assert result.assessment_passed is False
        assert result.mastery_updated is True

    def test_mastery_fields_persisted(self):
        attempt = self._make_attempt(mastery_before=50.0, mastery_after=75.0)
        result = _build_reentry_result(attempt)
        assert result.mastery_before == Decimal("50.00")
        assert result.mastery_after == Decimal("75.00")
