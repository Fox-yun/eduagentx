"""Unit tests for profile_merge service logic.

Verifies:
  - Numeric dimension merge: confidence-weighted average
  - List dimension merge (resource_preference): frequency counting
  - Dict dimension merge (error_pattern): accumulation with decay
  - String dimension merge (learning_pace): higher confidence wins
  - Average confidence calculation
  - _merge_values handles None old values

Run with:
    pytest tests/unit/test_profile_merge.py -v
"""

from __future__ import annotations

import pytest

from app.services.profile_merge import (
    ProfileEvidenceInput,
    _average_confidence,
    _merge_values,
)


class TestMergeNumericValues:
    """Test _merge_values for numeric (float/int) dimensions."""

    def test_weighted_average(self):
        result = _merge_values(
            old_value=0.4,
            old_confidence=0.6,
            new_value=0.8,
            new_confidence=0.4,
            dimension="knowledge_depth",
        )
        expected = (0.4 * 0.6 + 0.8 * 0.4) / (0.6 + 0.4)
        assert result == pytest.approx(expected)

    def test_old_value_none_uses_new(self):
        result = _merge_values(
            old_value=None,
            old_confidence=0.0,
            new_value=0.7,
            new_confidence=0.5,
            dimension="knowledge_depth",
        )
        assert result == 0.7

    def test_both_confidences_zero(self):
        result = _merge_values(
            old_value=0.3,
            old_confidence=0.0,
            new_value=0.7,
            new_confidence=0.0,
            dimension="knowledge_depth",
        )
        # When total_conf == 0, returns new_value
        assert result == 0.7

    def test_integer_values(self):
        result = _merge_values(
            old_value=1,
            old_confidence=0.5,
            new_value=3,
            new_confidence=0.5,
            dimension="knowledge_depth",
        )
        assert result == pytest.approx(2.0)


class TestMergeListValues:
    """Test _merge_values for list dimensions (resource_preference)."""

    def test_merge_lists_with_frequency(self):
        old = ["video", "reading"]
        new = ["video", "project"]
        result = _merge_values(
            old_value=old,
            old_confidence=0.5,
            new_value=new,
            new_confidence=0.8,
            dimension="resource_preference",
        )
        # video should have highest weighted count: 0.5 + 0.8 = 1.3
        assert "video" in result
        assert isinstance(result, list)

    def test_merge_list_old_none(self):
        result = _merge_values(
            old_value=None,
            old_confidence=0.0,
            new_value=["video"],
            new_confidence=0.5,
            dimension="resource_preference",
        )
        assert result == ["video"]

    def test_merge_list_limits_to_five(self):
        old = ["a", "b", "c", "d", "e"]
        new = ["f", "g", "h"]
        result = _merge_values(
            old_value=old,
            old_confidence=0.5,
            new_value=new,
            new_confidence=0.5,
            dimension="resource_preference",
        )
        assert len(result) <= 5


class TestMergeDictValues:
    """Test _merge_values for dict dimensions (error_pattern)."""

    def test_merge_dicts_with_decay(self):
        old = {"loops": 1.0}
        new = {"recursion": 0.8}
        result = _merge_values(
            old_value=old,
            old_confidence=0.5,
            new_value=new,
            new_confidence=0.8,
            dimension="error_pattern",
        )
        # old loops: 1.0 * 0.85 = 0.85
        # new recursion: 0 + 0.8 * 0.8 = 0.64
        assert "loops" in result
        assert "recursion" in result
        assert result["loops"] == pytest.approx(0.85)
        assert result["recursion"] == pytest.approx(0.64)

    def test_merge_dict_same_key_accumulates(self):
        old = {"loops": 1.0}
        new = {"loops": 0.8}
        result = _merge_values(
            old_value=old,
            old_confidence=0.5,
            new_value=new,
            new_confidence=0.8,
            dimension="error_pattern",
        )
        # old loops: 1.0 * 0.85 = 0.85
        # new loops: 0.85 + 0.8 * 0.8 = 0.85 + 0.64 = 1.49
        assert result["loops"] == pytest.approx(1.49)

    def test_merge_dict_filters_low_values(self):
        """Values below 0.1 threshold are filtered out."""
        old = {"low": 0.05}
        new = {}
        result = _merge_values(
            old_value=old,
            old_confidence=0.5,
            new_value=new,
            new_confidence=0.5,
            dimension="error_pattern",
        )
        # old low: 0.05 * 0.85 = 0.0425 < 0.1, filtered
        assert "low" not in result

    def test_merge_dict_old_none(self):
        """When old_value is None, _merge_values returns new_value directly."""
        result = _merge_values(
            old_value=None,
            old_confidence=0.0,
            new_value={"loops": 0.8},
            new_confidence=0.7,
            dimension="error_pattern",
        )
        # The early return for old_value is None gives back new_value as-is
        assert result == {"loops": 0.8}


class TestMergeStringValues:
    """Test _merge_values for string dimensions (learning_pace)."""

    def test_new_higher_confidence_wins(self):
        result = _merge_values(
            old_value="slow",
            old_confidence=0.3,
            new_value="fast",
            new_confidence=0.7,
            dimension="learning_pace",
        )
        assert result == "fast"

    def test_old_higher_confidence_kept(self):
        result = _merge_values(
            old_value="slow",
            old_confidence=0.8,
            new_value="fast",
            new_confidence=0.3,
            dimension="learning_pace",
        )
        assert result == "slow"

    def test_equal_confidence_new_wins(self):
        result = _merge_values(
            old_value="slow",
            old_confidence=0.5,
            new_value="fast",
            new_confidence=0.5,
            dimension="learning_pace",
        )
        assert result == "fast"


class TestAverageConfidence:
    def test_empty(self):
        assert _average_confidence({}) == 0.0

    def test_single_dimension(self):
        assert _average_confidence({"a": {"confidence": 0.7}}) == 0.7

    def test_multiple_dimensions(self):
        dims = {"a": {"confidence": 0.6}, "b": {"confidence": 0.8}, "c": {"confidence": 0.4}}
        assert _average_confidence(dims) == pytest.approx(0.6)

    def test_missing_confidence_key(self):
        dims = {"a": {"confidence": 0.6}, "b": {}}
        assert _average_confidence(dims) == pytest.approx(0.3)

    def test_none_dimensions(self):
        assert _average_confidence(None) == 0.0  # type: ignore[arg-type]


class TestProfileEvidenceInput:
    """Test the ProfileEvidenceInput dataclass."""

    def test_create_with_defaults(self):
        ev = ProfileEvidenceInput(
            dimension="knowledge_depth",
            value=0.5,
            confidence=0.8,
            evidence_type="conversation_profile",
            evidence_id="sess-1",
        )
        assert ev.evidence_text == ""
        assert ev.metadata is None

    def test_create_with_all_fields(self):
        ev = ProfileEvidenceInput(
            dimension="error_pattern",
            value={"loops": 0.7},
            confidence=0.6,
            evidence_type="assessment_attempt",
            evidence_id="att-1",
            evidence_text="Weak in loops",
            metadata={"node": "Python Basics"},
        )
        assert ev.evidence_text == "Weak in loops"
        assert ev.metadata == {"node": "Python Basics"}

    def test_frozen_dataclass(self):
        ev = ProfileEvidenceInput(
            dimension="knowledge_depth",
            value=0.5,
            confidence=0.8,
            evidence_type="conversation_profile",
            evidence_id="sess-1",
        )
        with pytest.raises(AttributeError):
            ev.confidence = 0.9  # type: ignore[misc]

    def test_accepts_various_value_types(self):
        """ProfileEvidenceInput should accept float, str, list, dict values."""
        for value in [0.5, "fast", ["video"], {"loops": 0.7}]:
            ev = ProfileEvidenceInput(
                dimension="test",
                value=value,
                confidence=0.5,
                evidence_type="test",
                evidence_id="test",
            )
            assert ev.value == value
