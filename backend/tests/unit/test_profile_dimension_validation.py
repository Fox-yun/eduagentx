"""Unit tests for profile dimension validation.

Verifies:
  - PROFILE_DIMENSIONS contains exactly 8 dimensions
  - All dimension names match expected values
  - error_pattern accepts dict values
  - resource_preference accepts list values
  - Manual correction validates dimension against enum

Run with:
    pytest tests/unit/test_profile_dimension_validation.py -v
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.common.enums import PROFILE_DIMENSIONS, ProfileEvidenceType, ProfileStatus
from app.routers.profile import ManualCorrectionRequest, ProfileDimension


class TestProfileDimensions:
    """Test the PROFILE_DIMENSIONS constant."""

    def test_exactly_eight_dimensions(self):
        assert len(PROFILE_DIMENSIONS) == 8

    def test_dimensions_are_strings(self):
        for dim in PROFILE_DIMENSIONS:
            assert isinstance(dim, str)

    def test_expected_dimensions_present(self):
        expected = {
            "knowledge_depth",
            "prerequisite_mastery",
            "concept_grasp",
            "problem_solving",
            "practice_ability",
            "learning_pace",
            "resource_preference",
            "error_pattern",
        }
        assert set(PROFILE_DIMENSIONS) == expected

    def test_dimensions_are_unique(self):
        assert len(PROFILE_DIMENSIONS) == len(set(PROFILE_DIMENSIONS))


class TestDimensionValueTypes:
    """Test that different value types are accepted for different dimensions."""

    def test_error_pattern_accepts_dict(self):
        req = ManualCorrectionRequest(
            dimension="error_pattern",
            value={"loops": 0.8, "recursion": 0.5},
        )
        assert isinstance(req.value, dict)

    def test_resource_preference_accepts_list(self):
        req = ManualCorrectionRequest(
            dimension="resource_preference",
            value=["video", "reading", "project"],
        )
        assert isinstance(req.value, list)

    def test_learning_pace_accepts_string(self):
        req = ManualCorrectionRequest(
            dimension="learning_pace",
            value="moderate",
        )
        assert isinstance(req.value, str)

    def test_knowledge_depth_accepts_float(self):
        req = ManualCorrectionRequest(
            dimension="knowledge_depth",
            value=0.65,
        )
        assert isinstance(req.value, float)

    def test_knowledge_depth_accepts_int(self):
        req = ManualCorrectionRequest(
            dimension="knowledge_depth",
            value=1,
        )
        assert req.value == 1


class TestProfileDimensionLiteral:
    """Test the ProfileDimension Literal type used in the router."""

    def test_all_dimensions_in_literal(self):
        from typing import get_args

        literal_dims = set(get_args(ProfileDimension))
        assert literal_dims == set(PROFILE_DIMENSIONS)

    @pytest.mark.parametrize("dim", list(PROFILE_DIMENSIONS))
    def test_each_dimension_accepted_by_request(self, dim: str):
        req = ManualCorrectionRequest(dimension=dim, value=0.5)  # type: ignore[arg-type]
        assert req.dimension == dim

    def test_invalid_dimension_rejected(self):
        with pytest.raises(ValidationError):
            ManualCorrectionRequest(dimension="nonexistent", value=0.5)  # type: ignore[arg-type]


class TestProfileEnums:
    """Test profile-related enums."""

    def test_profile_status_values(self):
        assert ProfileStatus.ACTIVE.value == "active"
        assert ProfileStatus.PROVISIONAL.value == "provisional"
        assert ProfileStatus.ARCHIVED.value == "archived"

    def test_evidence_type_values(self):
        assert ProfileEvidenceType.CONVERSATION_PROFILE.value == "conversation_profile"
        assert ProfileEvidenceType.ASSESSMENT_ATTEMPT.value == "assessment_attempt"
        assert ProfileEvidenceType.DIAGNOSTIC_RESULT.value == "diagnostic_result"
        assert ProfileEvidenceType.LEARNING_BEHAVIOR.value == "learning_behavior"
        assert ProfileEvidenceType.MANUAL_CORRECTION.value == "manual_correction"

    def test_evidence_types_are_unique(self):
        values = [e.value for e in ProfileEvidenceType]
        assert len(values) == len(set(values))
