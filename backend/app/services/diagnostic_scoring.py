"""Pure diagnostic scoring functions with no database dependency.

All functions are stateless and operate on provided data only,
making them fully deterministic and testable.

Shared objective scoring functions are imported from answer_scoring:
  score_single_choice, score_multiple_choice, score_true_false, score_short_answer
Diagnostic-specific aggregation and readiness levels remain here.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.services.answer_scoring import (
    PROVISIONAL_FEEDBACK,
    PROVISIONAL_WEIGHT,
    ScoredAnswer,
    _d,
    score_single_choice,
    score_multiple_choice,
    score_true_false,
    score_short_answer,
)

# Re-export shared scoring symbols for backward compatibility
__all__ = [
    "ScoredAnswer",
    "score_single_choice",
    "score_multiple_choice",
    "score_true_false",
    "score_short_answer",
    "AggregatedResult",
    "aggregate_results",
    "LEVEL_BEGINNER",
    "LEVEL_INTERMEDIATE",
    "LEVEL_PROFICIENT",
    "LEVEL_ADVANCED",
]

# Readiness level thresholds
LEVEL_BEGINNER = 0.0
LEVEL_INTERMEDIATE = 40.0
LEVEL_PROFICIENT = 70.0
LEVEL_ADVANCED = 85.0


@dataclass(frozen=True)
class AggregatedResult:
    """Aggregated diagnostic scoring result."""

    total_score: Decimal
    total_max_score: Decimal
    percentage: float
    dimension_scores: dict[str, float]
    readiness_level: str


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
