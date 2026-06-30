"""Fixtures for diagnostic contract tests."""

from __future__ import annotations

import json
import uuid

import pytest
from pydantic import ValidationError

from app.routers.diagnostics import AnswerSubmitItem


@pytest.fixture
def diagnostic_question_json() -> str:
    """A sample single_choice question serialized as JSON (public DTO)."""
    return json.dumps(
        {
            "question_id": str(uuid.uuid4()),
            "question_type": "single_choice",
            "prompt": "What is 2+2?",
            "required": True,
            "options": [
                {"value": "3", "label": "Three"},
                {"value": "4", "label": "Four"},
            ],
            "dimension": "fundamentals",
            "max_score": 10,
        }
    )


@pytest.fixture
def full_diagnostic_quiz_json() -> dict:
    """Full quiz response payload."""
    return {
        "diagnostic_id": f"diag-{uuid.uuid4().hex[:8]}",
        "goal_id": str(uuid.uuid4()),
        "attempt_id": str(uuid.uuid4()),
        "status": "draft",
        "questions": [
            {
                "question_id": str(uuid.uuid4()),
                "question_type": "single_choice",
                "prompt": "测试问题？",
                "required": True,
                "options": [{"value": "a", "label": "选项A"}],
                "dimension": "basics",
                "max_score": 10,
            },
        ],
        "saved_answers": {},
        "result": None,
        "next_step": "diagnostic",
    }


@pytest.fixture
def diagnostic_submit_response_json() -> dict:
    """Submit response payload."""
    return {
        "attempt_id": str(uuid.uuid4()),
        "status": "grading",
        "task_id": str(uuid.uuid4()),
    }


@pytest.fixture
def diagnostic_result_json() -> dict:
    """Result response payload."""
    return {
        "percentage": 85.0,
        "dimension_scores": {
            "basics": 90.0,
            "advanced": 80.0,
        },
        "readiness_level": "proficient",
        "grading_quality": "final",
    }


@pytest.fixture
def diagnostic_submit_validation_errors() -> list[dict]:
    """Collect validation errors when submitting with unknown fields.

    Pydantic v2 gives precise error details.
    """
    try:
        AnswerSubmitItem(
            question_id=str(uuid.uuid4()),
            answer="test",
            unknown_field="should_not_be_allowed",
        )
        return []
    except ValidationError as e:
        return [{"field": err.get("loc", ("",))[-1], "msg": err.get("msg", "")} for err in e.errors()]
