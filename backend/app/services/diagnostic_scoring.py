"""Pure diagnostic scoring functions with no database dependency.

All functions are stateless and operate on provided data only,
making them fully deterministic and testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

# Readiness level thresholds
LEVEL_BEGINNER = 0.0
LEVEL_INTERMEDIATE = 40.0
LEVEL_PROFICIENT = 70.0
LEVEL_ADVANCED = 85.0

PROVISIONAL_WEIGHT = Decimal("0.5")
PROVISIONAL_FEEDBACK = "自动评分服务暂时不可用，当前结果为临时评分，后续可能重新评估。"


@dataclass(frozen=True)
class ScoredAnswer:
    """Result of scoring a single diagnostic question."""

    question_id: str
    score: Decimal
    max_score: Decimal
    is_correct: bool | None
    feedback: str | None
    grading_source: str  # "program" | "llm" | "fallback"
    grading_status: str  # "graded" | "provisional" | "failed"


@dataclass(frozen=True)
class AggregatedResult:
    """Aggregated diagnostic scoring result."""

    total_score: Decimal
    total_max_score: Decimal
    percentage: float
    dimension_scores: dict[str, float]
    readiness_level: str


def _d(value: float | str | Decimal) -> Decimal:
    """Normalize to Decimal with 2 decimal places."""
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _readiness_level(percentage: float) -> str:
    """Map a percentage score to a readiness level."""
    if percentage < LEVEL_INTERMEDIATE:
        return "beginner"
    elif percentage < LEVEL_PROFICIENT:
        return "intermediate"
    elif percentage < LEVEL_ADVANCED:
        return "proficient"
    else:
        return "advanced"


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
        # Validate range
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
        # LLM output invalid — fall back to provisional
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


def aggregate_results(
    scored_answers: list[ScoredAnswer],
    questions: list[dict[str, Any]],
) -> AggregatedResult:
    """Aggregate individual scored answers into a complete result.

    Args:
        scored_answers: List of scored answers (question_id must match).
        questions: List of question dicts with 'id', 'dimension', 'max_score'.

    Returns:
        AggregatedResult with totals, per-dimension scores, and readiness level.
    """
    # Build lookup
    q_map: dict[str, dict[str, Any]] = {q["id"]: q for q in questions}

    total_score = Decimal("0.00")
    total_max = Decimal("0.00")
    dim_scores: dict[str, Decimal] = {}
    dim_maxes: dict[str, Decimal] = {}

    for sa in scored_answers:
        total_score += sa.score
        total_max += sa.max_score
        q = q_map.get(sa.question_id, {})
        dim = q.get("dimension") or "general"
        dim_scores[dim] = dim_scores.get(dim, Decimal("0.00")) + sa.score
        dim_maxes[dim] = dim_maxes.get(dim, Decimal("0.00")) + sa.max_score

    # Build per-dimension percentages (only for dimensions with questions)
    dim_pcts: dict[str, float] = {}
    for dim in dim_scores:
        if dim_maxes[dim] > 0:
            pct = float(
                (dim_scores[dim] / dim_maxes[dim] * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            )
            dim_pcts[dim] = pct

    overall_pct = (
        float((total_score / total_max * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        if total_max > 0
        else 0.0
    )

    return AggregatedResult(
        total_score=total_score,
        total_max_score=total_max,
        percentage=overall_pct,
        dimension_scores=dim_pcts,
        readiness_level=_readiness_level(overall_pct),
    )
