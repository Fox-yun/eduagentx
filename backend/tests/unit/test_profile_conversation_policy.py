"""Unit tests for profile conversation finalize policy.

Verifies:
  - can_finalize enforces minimum 3 turns
  - can_finalize enforces minimum 6 dimensions covered
  - can_finalize enforces minimum 0.65 average confidence
  - Max turns forces ready_to_finalize
  - Average confidence calculation handles edge cases

Run with:
    pytest tests/unit/test_profile_conversation_policy.py -v
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.profile_conversation import (
    MAX_TURNS,
    MIN_AVG_CONFIDENCE,
    MIN_DIMENSIONS_COVERED,
    MIN_TURNS,
    ProfileConversationService,
    _average_confidence,
)


def _make_session(
    turn_count: int = 0,
    extracted_dimensions: dict | None = None,
) -> SimpleNamespace:
    """Create a mock session with the minimal fields needed by can_finalize."""
    return SimpleNamespace(
        turn_count=turn_count,
        extracted_dimensions=extracted_dimensions or {},
    )


def _make_dimensions(count: int, confidence: float = 0.7) -> dict:
    """Create a dict of N dimensions with the given confidence."""
    all_dims = [
        "knowledge_depth",
        "prerequisite_mastery",
        "concept_grasp",
        "problem_solving",
        "practice_ability",
        "learning_pace",
        "resource_preference",
        "error_pattern",
    ]
    return {dim: {"value": 0.5, "confidence": confidence} for dim in all_dims[:count]}


class TestCanFinalize:
    def test_insufficient_turns(self):
        session = _make_session(turn_count=MIN_TURNS - 1, extracted_dimensions=_make_dimensions(8))
        assert ProfileConversationService.can_finalize(session) is False

    def test_exact_min_turns_with_enough_dims_and_confidence(self):
        session = _make_session(turn_count=MIN_TURNS, extracted_dimensions=_make_dimensions(6, 0.7))
        assert ProfileConversationService.can_finalize(session) is True

    def test_insufficient_dimensions(self):
        session = _make_session(turn_count=MIN_TURNS, extracted_dimensions=_make_dimensions(5, 0.7))
        assert ProfileConversationService.can_finalize(session) is False

    def test_exact_min_dimensions(self):
        session = _make_session(turn_count=MIN_TURNS, extracted_dimensions=_make_dimensions(6, 0.7))
        assert ProfileConversationService.can_finalize(session) is True

    def test_low_confidence(self):
        session = _make_session(
            turn_count=MIN_TURNS,
            extracted_dimensions=_make_dimensions(8, confidence=0.5),
        )
        assert ProfileConversationService.can_finalize(session) is False

    def test_exact_min_confidence(self):
        session = _make_session(
            turn_count=MIN_TURNS,
            extracted_dimensions=_make_dimensions(6, confidence=MIN_AVG_CONFIDENCE),
        )
        assert ProfileConversationService.can_finalize(session) is True

    def test_high_confidence_all_dimensions(self):
        session = _make_session(
            turn_count=MAX_TURNS,
            extracted_dimensions=_make_dimensions(8, confidence=0.9),
        )
        assert ProfileConversationService.can_finalize(session) is True

    def test_empty_extracted_dimensions(self):
        session = _make_session(turn_count=MIN_TURNS, extracted_dimensions={})
        assert ProfileConversationService.can_finalize(session) is False

    def test_none_extracted_dimensions(self):
        session = _make_session(turn_count=MIN_TURNS, extracted_dimensions=None)
        assert ProfileConversationService.can_finalize(session) is False


class TestAverageConfidence:
    def test_empty_dict(self):
        assert _average_confidence({}) == 0.0

    def test_single_dimension(self):
        assert _average_confidence({"d": {"confidence": 0.8}}) == 0.8

    def test_multiple_dimensions(self):
        dims = {"a": {"confidence": 0.6}, "b": {"confidence": 0.8}}
        assert _average_confidence(dims) == pytest.approx(0.7)

    def test_missing_confidence_key_defaults_to_zero(self):
        dims = {"a": {"confidence": 0.6}, "b": {}}
        assert _average_confidence(dims) == pytest.approx(0.3)

    def test_none_input(self):
        assert _average_confidence(None) == 0.0  # type: ignore[arg-type]


class TestShouldFinalize:
    """Test the private _should_finalize method via the service."""

    def _make_service(self):
        return ProfileConversationService.__new__(ProfileConversationService)

    def test_below_min_turns(self):
        svc = self._make_service()
        assert svc._should_finalize(MIN_TURNS - 1, 8, 0.9) is False

    def test_at_max_turns(self):
        svc = self._make_service()
        assert svc._should_finalize(MAX_TURNS, 0, 0.0) is True

    def test_above_max_turns(self):
        svc = self._make_service()
        assert svc._should_finalize(MAX_TURNS + 1, 0, 0.0) is True

    def test_enough_dims_and_confidence(self):
        svc = self._make_service()
        assert svc._should_finalize(MIN_TURNS, MIN_DIMENSIONS_COVERED, MIN_AVG_CONFIDENCE) is True

    def test_not_enough_dims(self):
        svc = self._make_service()
        assert svc._should_finalize(MIN_TURNS, MIN_DIMENSIONS_COVERED - 1, 0.9) is False

    def test_not_enough_confidence(self):
        svc = self._make_service()
        assert svc._should_finalize(MIN_TURNS, MIN_DIMENSIONS_COVERED, MIN_AVG_CONFIDENCE - 0.01) is False


class TestGetCoveredDimensions:
    """Test the _get_covered_dimensions helper."""

    def _make_service(self):
        return ProfileConversationService.__new__(ProfileConversationService)

    def test_empty(self):
        svc = self._make_service()
        assert svc._get_covered_dimensions({}) == []

    def test_filters_zero_confidence(self):
        svc = self._make_service()
        dims = {"a": {"confidence": 0.5}, "b": {"confidence": 0}, "c": {"confidence": 0.0}}
        assert set(svc._get_covered_dimensions(dims)) == {"a"}

    def test_all_covered(self):
        svc = self._make_service()
        dims = {"a": {"confidence": 0.5}, "b": {"confidence": 0.8}}
        assert set(svc._get_covered_dimensions(dims)) == {"a", "b"}


class TestMergeExtracted:
    """Test the _merge_extracted helper for JSON merge logic."""

    def _make_service(self):
        return ProfileConversationService.__new__(ProfileConversationService)

    def test_merge_new_dimension(self):
        svc = self._make_service()
        current = {}
        new = [{"dimension": "knowledge_depth", "value": 0.3, "confidence": 0.5}]
        result = svc._merge_extracted(current, new)
        assert "knowledge_depth" in result
        assert result["knowledge_depth"]["value"] == 0.3

    def test_merge_higher_confidence_replaces(self):
        svc = self._make_service()
        current = {"knowledge_depth": {"value": 0.2, "confidence": 0.4}}
        new = [{"dimension": "knowledge_depth", "value": 0.5, "confidence": 0.8}]
        result = svc._merge_extracted(current, new)
        assert result["knowledge_depth"]["value"] == 0.5
        assert result["knowledge_depth"]["confidence"] == 0.8

    def test_merge_lower_confidence_keeps_old(self):
        svc = self._make_service()
        current = {"knowledge_depth": {"value": 0.5, "confidence": 0.8}}
        new = [{"dimension": "knowledge_depth", "value": 0.2, "confidence": 0.4}]
        result = svc._merge_extracted(current, new)
        assert result["knowledge_depth"]["value"] == 0.5
        assert result["knowledge_depth"]["confidence"] == 0.8

    def test_merge_equal_confidence_replaces(self):
        svc = self._make_service()
        current = {"knowledge_depth": {"value": 0.5, "confidence": 0.6}}
        new = [{"dimension": "knowledge_depth", "value": 0.7, "confidence": 0.6}]
        result = svc._merge_extracted(current, new)
        assert result["knowledge_depth"]["value"] == 0.7

    def test_merge_does_not_mutate_original(self):
        """E0-A2: merge should not mutate the original dict in-place."""
        svc = self._make_service()
        current = {"knowledge_depth": {"value": 0.5, "confidence": 0.8}}
        new = [{"dimension": "learning_pace", "value": "fast", "confidence": 0.6}]
        result = svc._merge_extracted(current, new)
        assert "learning_pace" not in current
        assert "learning_pace" in result
