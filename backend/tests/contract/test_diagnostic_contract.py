"""Contract tests for diagnostic API — verify DTO safety and field completeness."""
from __future__ import annotations

import json

import pytest


class TestDiagnosticQuestionDto:
    """Questions returned via public API must NOT leak scoring internals."""

    def test_question_response_omits_correct_answer(self, diagnostic_question_json: str):
        """correct_answer must not appear in the public DTO."""
        assert "correct_answer" not in diagnostic_question_json

    def test_question_response_omits_rubric(self, diagnostic_question_json: str):
        """rubric must not appear in the public DTO."""
        assert "rubric" not in diagnostic_question_json

    def test_question_response_omits_grading_internals(self, diagnostic_question_json: str):
        """grading_prompt and reference_answer must not appear."""
        assert "grading_prompt" not in diagnostic_question_json
        assert "reference_answer" not in diagnostic_question_json

    def test_deep_serialization_no_leak(self, diagnostic_question_json: str):
        """Stringify entire JSON to catch nested leaks."""
        raw = diagnostic_question_json
        for forbidden in ("correct_answer", "rubric", "grading_prompt", "reference_answer"):
            assert forbidden not in json.dumps(raw), f"Found leaked field: {forbidden}"


class TestDiagnosticContract:
    """End-to-end contract verification for the public diagnostic API."""

    def test_quiz_response_structure(self, full_diagnostic_quiz_json: dict):
        """Quiz endpoint returns expected top-level fields."""
        body = full_diagnostic_quiz_json
        assert "diagnostic_id" in body
        assert "attempt_id" in body
        assert "goal_id" in body
        assert "status" in body
        assert "questions" in body
        assert isinstance(body["questions"], list)

    def test_quiz_attempt_id_present(self, full_diagnostic_quiz_json: dict):
        """Quiz response must include attempt_id."""
        assert full_diagnostic_quiz_json["attempt_id"] is not None
        assert len(full_diagnostic_quiz_json["attempt_id"]) > 0

    def test_quiz_status_valid(self, full_diagnostic_quiz_json: dict):
        """Quiz status must be a valid value."""
        valid = {"draft", "submitted", "grading", "completed", "failed"}
        assert full_diagnostic_quiz_json["status"] in valid

    def test_submit_response_required_fields(self, diagnostic_submit_response_json: dict):
        """Submit response must contain attempt_id, status, task_id."""
        body = diagnostic_submit_response_json
        assert "attempt_id" in body
        assert "status" in body
        assert "task_id" in body

    def test_submit_status_valid(self, diagnostic_submit_response_json: dict):
        """Submit status should be grading or completed."""
        assert diagnostic_submit_response_json["status"] in ("grading", "completed")

    def test_result_response_structure(self, diagnostic_result_json: dict):
        """Result endpoint returns required analysis fields."""
        body = diagnostic_result_json
        assert "percentage" in body
        assert "dimension_scores" in body
        assert "readiness_level" in body
        assert "grading_quality" in body

    def test_result_no_internal_fields(self, diagnostic_result_json: dict):
        """Result must not expose scoring internals."""
        body = diagnostic_result_json
        assert "rubric" not in body
        assert "correct_answer" not in body
        assert "reference_answer" not in body

    def test_submit_rejects_unknown_fields(self, diagnostic_submit_validation_errors: list[dict]):
        """Unknown fields in submit body should be rejected."""
        for error in diagnostic_submit_validation_errors:
            assert any(
                msg in str(error.get("msg", "")).lower()
                for msg in ("extra", "unexpected", "unknown", "field")
            ), f"Validation error should mention extra/unknown field: {error}"
