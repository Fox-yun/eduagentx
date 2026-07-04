"""Unit tests for profile conversation API request/response schemas.

Verifies:
  - CreateConversationRequest accepts valid input and rejects extra fields
  - SendMessageRequest accepts valid input and rejects extra fields
  - ManualCorrectionRequest validates dimension enum and value types
  - Response models serialise correctly

Run with:
    pytest tests/unit/test_profile_conversation_schema.py -v
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.routers.profile import (
    CreateConversationRequest,
    CreateConversationResponse,
    FinalizeResponse,
    ManualCorrectionRequest,
    ProfileDimension,
    ProfileSummaryResponse,
    SendMessageRequest,
    SendMessageResponse,
)


class TestCreateConversationRequest:
    def test_valid_request(self):
        req = CreateConversationRequest(learning_goal="学 Python")
        assert req.learning_goal == "学 Python"
        assert req.target_context is None
        assert req.learning_goal_id is None

    def test_valid_request_with_all_fields(self):
        req = CreateConversationRequest(
            learning_goal="学 Python",
            target_context="在职转行",
            learning_goal_id="goal-123",
        )
        assert req.learning_goal == "学 Python"
        assert req.target_context == "在职转行"
        assert req.learning_goal_id == "goal-123"

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError, match="extra"):
            CreateConversationRequest(learning_goal="学 Python", unexpected_field="bad")

    def test_rejects_empty_learning_goal(self):
        with pytest.raises(ValidationError):
            CreateConversationRequest(learning_goal="")

    def test_rejects_missing_learning_goal(self):
        with pytest.raises(ValidationError):
            CreateConversationRequest()


class TestSendMessageRequest:
    def test_valid_request(self):
        req = SendMessageRequest(message="我基础比较薄弱")
        assert req.message == "我基础比较薄弱"

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError, match="extra"):
            SendMessageRequest(message="hello", extra="bad")

    def test_rejects_empty_message(self):
        with pytest.raises(ValidationError):
            SendMessageRequest(message="")


class TestManualCorrectionRequest:
    def test_valid_numeric_value(self):
        req = ManualCorrectionRequest(
            dimension="knowledge_depth",
            value=0.75,
        )
        assert req.dimension == "knowledge_depth"
        assert req.value == 0.75
        assert req.confidence == 1.0
        assert req.reason is None

    def test_valid_string_value(self):
        req = ManualCorrectionRequest(
            dimension="learning_pace",
            value="fast",
        )
        assert req.value == "fast"

    def test_valid_list_value(self):
        req = ManualCorrectionRequest(
            dimension="resource_preference",
            value=["video", "project"],
        )
        assert req.value == ["video", "project"]

    def test_valid_dict_value_for_error_pattern(self):
        req = ManualCorrectionRequest(
            dimension="error_pattern",
            value={"loops": 0.8, "recursion": 0.6},
        )
        assert req.value == {"loops": 0.8, "recursion": 0.6}

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError, match="extra"):
            ManualCorrectionRequest(
                dimension="knowledge_depth",
                value=0.5,
                extra="bad",
            )

    def test_rejects_invalid_dimension(self):
        with pytest.raises(ValidationError):
            ManualCorrectionRequest(
                dimension="invalid_dimension",
                value=0.5,
            )

    @pytest.mark.parametrize(
        "dim",
        [
            "knowledge_depth",
            "prerequisite_mastery",
            "concept_grasp",
            "problem_solving",
            "practice_ability",
            "learning_pace",
            "resource_preference",
            "error_pattern",
        ],
    )
    def test_all_eight_dimensions_accepted(self, dim: str):
        req = ManualCorrectionRequest(dimension=dim, value=0.5)  # type: ignore[arg-type]
        assert req.dimension == dim

    def test_confidence_range_validation(self):
        with pytest.raises(ValidationError):
            ManualCorrectionRequest(dimension="knowledge_depth", value=0.5, confidence=1.5)
        with pytest.raises(ValidationError):
            ManualCorrectionRequest(dimension="knowledge_depth", value=0.5, confidence=-0.1)

    def test_confidence_boundary_values(self):
        req = ManualCorrectionRequest(dimension="knowledge_depth", value=0.5, confidence=0.0)
        assert req.confidence == 0.0
        req = ManualCorrectionRequest(dimension="knowledge_depth", value=0.5, confidence=1.0)
        assert req.confidence == 1.0


class TestResponseModels:
    def test_create_conversation_response(self):
        resp = CreateConversationResponse(
            session_id="sess-1",
            status="active",
            assistant_message="你好！",
        )
        assert resp.session_id == "sess-1"
        assert resp.status == "active"

    def test_send_message_response(self):
        resp = SendMessageResponse(
            assistant_message="下个问题",
            extracted_dimensions={"knowledge_depth": {"value": 0.3, "confidence": 0.5}},
            missing_dimensions=["learning_pace"],
            ready_to_finalize=False,
        )
        assert resp.assistant_message == "下个问题"
        assert "knowledge_depth" in resp.extracted_dimensions

    def test_finalize_response(self):
        resp = FinalizeResponse(
            profile_id="p-1",
            profile_version=1,
            dimensions={"knowledge_depth": {"value": 0.5, "confidence": 0.7, "source": "conversation_profile"}},
            summary="测试摘要",
            confidence=0.7,
        )
        assert resp.profile_version == 1
        assert resp.summary == "测试摘要"

    def test_profile_summary_response(self):
        resp = ProfileSummaryResponse(
            profile_id="p-1",
            user_id="u-1",
            status="active",
            profile_version=2,
            dimensions={},
            summary=None,
            confidence=0.5,
        )
        assert resp.status == "active"
        assert resp.summary is None


class TestProfileDimensionLiteral:
    """Verify the ProfileDimension literal contains exactly 8 dimensions."""

    def test_dimension_count(self):
        from typing import get_args

        dims = get_args(ProfileDimension)
        assert len(dims) == 8

    def test_dimensions_match_enum(self):
        from typing import get_args

        from app.common.enums import PROFILE_DIMENSIONS

        literal_dims = set(get_args(ProfileDimension))
        assert literal_dims == set(PROFILE_DIMENSIONS)
