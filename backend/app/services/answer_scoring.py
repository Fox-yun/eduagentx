"""Shared answer scoring functions for objective question types.

These pure, stateless functions are used by both Diagnostic and Assessment
submission flows. They operate on provided data only and have no database
dependency, making them fully deterministic and testable.

Supported types:
  - single_choice: exact string match = full score or 0
  - multiple_choice: strict set equality = full score or 0
  - true_false: boolean identity = full score or 0
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

PROVISIONAL_WEIGHT = Decimal("0.5")
PROVISIONAL_FEEDBACK = "自动评分服务暂时不可用，当前结果为临时评分，后续可能重新评估。"


@dataclass(frozen=True)
class ScoredAnswer:
    """Result of scoring a single question."""

    question_id: str
    score: Decimal
    max_score: Decimal
    is_correct: bool | None
    feedback: str | None
    grading_source: str  # "program" | "llm" | "fallback"
    grading_status: str  # "graded" | "provisional" | "failed"


def _d(value: float | str | Decimal) -> Decimal:
    """Normalize to Decimal with 2 decimal places."""
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def score_single_choice(
    answer: str,
    correct: str,
    max_score: Decimal,
) -> ScoredAnswer:
    """Score a single_choice question: exact match = full score, else 0."""
    is_correct = str(answer).strip() == str(correct).strip()
    score = _d(max_score) if is_correct else Decimal("0.00")
    return ScoredAnswer(
        question_id="",
        score=score,
        max_score=_d(max_score),
        is_correct=is_correct,
        feedback=None,
        grading_source="program",
        grading_status="graded",
    )


def score_multiple_choice(
    answer: list[str],
    correct: list[str],
    max_score: Decimal,
) -> ScoredAnswer:
    """Score a multiple_choice question: strict set equality."""
    selected = {str(a).strip() for a in answer}
    expected = {str(c).strip() for c in correct}
    is_correct = selected == expected
    score = _d(max_score) if is_correct else Decimal("0.00")
    return ScoredAnswer(
        question_id="",
        score=score,
        max_score=_d(max_score),
        is_correct=is_correct,
        feedback=None,
        grading_source="program",
        grading_status="graded",
    )


def score_true_false(
    answer: bool,
    correct: bool,
    max_score: Decimal,
) -> ScoredAnswer:
    """Score a true_false question: boolean equality."""
    is_correct = bool(answer) is bool(correct)
    score = _d(max_score) if is_correct else Decimal("0.00")
    return ScoredAnswer(
        question_id="",
        score=score,
        max_score=_d(max_score),
        is_correct=is_correct,
        feedback=None,
        grading_source="program",
        grading_status="graded",
    )


def score_short_answer(
    answer: str,
    llm_result: dict[str, Any] | None,
    max_score: Decimal,
) -> ScoredAnswer:
    """Score a short_answer question using LLM result.

    When llm_result is None (LLM unavailable), returns a provisional
    fallback score of 50% of max_score.
    """
    _d_max = _d(max_score)

    if llm_result is None:
        score = (_d_max * PROVISIONAL_WEIGHT).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return ScoredAnswer(
            question_id="",
            score=score,
            max_score=_d_max,
            is_correct=None,
            feedback=PROVISIONAL_FEEDBACK,
            grading_source="fallback",
            grading_status="provisional",
        )

    try:
        raw_score = llm_result.get("score")
        if raw_score is None:
            raise ValueError("Missing 'score' in LLM result")
        score = _d(raw_score)
        if score < Decimal("0.00") or score > _d_max:
            raise ValueError(f"Score {score} out of range [0, {_d_max}]")

        feedback = str(llm_result.get("feedback", "")) or None
        return ScoredAnswer(
            question_id="",
            score=score,
            max_score=_d_max,
            is_correct=None,
            feedback=feedback,
            grading_source="llm",
            grading_status="graded",
        )
    except (ValueError, TypeError, KeyError, InvalidOperation):
        score = (_d_max * PROVISIONAL_WEIGHT).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return ScoredAnswer(
            question_id="",
            score=score,
            max_score=_d_max,
            is_correct=None,
            feedback=PROVISIONAL_FEEDBACK,
            grading_source="fallback",
            grading_status="provisional",
        )
