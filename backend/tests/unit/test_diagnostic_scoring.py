"""Unit tests for diagnostic scoring functions."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.diagnostic_scoring import (
    ScoredAnswer,
    aggregate_results,
    score_multiple_choice,
    score_short_answer,
    score_single_choice,
    score_true_false,
)


class TestScoreSingleChoice:
    def test_correct(self) -> None:
        result = score_single_choice("a", "a", Decimal("10"))
        assert result.score == Decimal("10.00")
        assert result.is_correct is True
        assert result.grading_source == "program"
        assert result.grading_status == "graded"

    def test_incorrect(self) -> None:
        result = score_single_choice("b", "a", Decimal("10"))
        assert result.score == Decimal("0.00")
        assert result.is_correct is False

    def test_whitespace_tolerance(self) -> None:
        result = score_single_choice("  a  ", "a", Decimal("5"))
        assert result.is_correct is True
        assert result.score == Decimal("5.00")

    def test_different_max_score(self) -> None:
        result = score_single_choice("a", "a", Decimal("20"))
        assert result.score == Decimal("20.00")


class TestScoreMultipleChoice:
    def test_exact_match(self) -> None:
        result = score_multiple_choice(["a", "b"], ["a", "b"], Decimal("10"))
        assert result.is_correct is True
        assert result.score == Decimal("10.00")

    def test_order_independent(self) -> None:
        result = score_multiple_choice(["b", "a"], ["a", "b"], Decimal("10"))
        assert result.is_correct is True
        assert result.score == Decimal("10.00")

    def test_extra_answer(self) -> None:
        result = score_multiple_choice(["a", "b", "c"], ["a", "b"], Decimal("10"))
        assert result.is_correct is False
        assert result.score == Decimal("0.00")

    def test_missing_answer(self) -> None:
        result = score_multiple_choice(["a"], ["a", "b"], Decimal("10"))
        assert result.is_correct is False
        assert result.score == Decimal("0.00")

    def test_all_wrong(self) -> None:
        result = score_multiple_choice(["c"], ["a", "b"], Decimal("10"))
        assert result.is_correct is False
        assert result.score == Decimal("0.00")

    def test_empty_selection(self) -> None:
        result = score_multiple_choice([], ["a", "b"], Decimal("10"))
        assert result.is_correct is False


class TestScoreTrueFalse:
    def test_true_correct(self) -> None:
        result = score_true_false(True, True, Decimal("5"))
        assert result.is_correct is True
        assert result.score == Decimal("5.00")

    def test_false_correct(self) -> None:
        result = score_true_false(False, False, Decimal("5"))
        assert result.is_correct is True

    def test_true_incorrect(self) -> None:
        result = score_true_false(True, False, Decimal("5"))
        assert result.is_correct is False
        assert result.score == Decimal("0.00")

    def test_false_incorrect(self) -> None:
        result = score_true_false(False, True, Decimal("5"))
        assert result.is_correct is False


class TestScoreShortAnswer:
    def test_valid_llm_result(self) -> None:
        result = score_short_answer("user answer", {"score": 8, "feedback": "Good answer"}, Decimal("10"))
        assert result.score == Decimal("8.00")
        assert result.grading_source == "llm"
        assert result.grading_status == "graded"
        assert result.feedback == "Good answer"

    def test_llm_result_without_feedback(self) -> None:
        result = score_short_answer("answer", {"score": 5}, Decimal("10"))
        assert result.score == Decimal("5.00")
        assert result.feedback is None

    def test_score_out_of_range_negative(self) -> None:
        result = score_short_answer("answer", {"score": -1, "feedback": "bad"}, Decimal("10"))
        assert result.grading_source == "fallback"
        assert result.grading_status == "provisional"
        assert result.score == Decimal("5.00")  # 50% fallback

    def test_score_exceeds_max(self) -> None:
        result = score_short_answer("answer", {"score": 15, "feedback": "too high"}, Decimal("10"))
        assert result.grading_source == "fallback"
        assert result.grading_status == "provisional"

    def test_missing_score_field(self) -> None:
        result = score_short_answer("answer", {"feedback": "no score"}, Decimal("10"))
        assert result.grading_source == "fallback"
        assert result.grading_status == "provisional"

    def test_invalid_type_in_result(self) -> None:
        result = score_short_answer("answer", {"score": "not a number"}, Decimal("10"))
        assert result.grading_source == "fallback"

    def test_llm_none_fallback(self) -> None:
        result = score_short_answer("answer", None, Decimal("10"))
        assert result.grading_source == "fallback"
        assert result.grading_status == "provisional"
        assert result.score == Decimal("5.00")
        assert "临时评分" in (result.feedback or "")

    def test_llm_none_no_final(self) -> None:
        """Provisional fallback must NOT be marked as final/graded."""
        result = score_short_answer("answer", None, Decimal("10"))
        assert result.grading_source != "program"
        assert result.grading_status != "graded"


class TestAggregateResults:
    def _make_q(self, qid: str, dim: str = "general", ms: float = 10) -> dict:
        return {"id": qid, "dimension": dim, "max_score": ms}

    def _make_sa(self, qid: str, score: float, ms: float = 10) -> ScoredAnswer:
        return ScoredAnswer(
            question_id=qid,
            score=Decimal(str(score)),
            max_score=Decimal(str(ms)),
            is_correct=score >= ms,
            feedback=None,
            grading_source="program",
            grading_status="graded",
        )

    def test_all_correct(self) -> None:
        qs = [self._make_q("q1", ms=10), self._make_q("q2", ms=10)]
        sas = [self._make_sa("q1", 10, ms=10), self._make_sa("q2", 10, ms=10)]
        result = aggregate_results(sas, qs)
        assert result.percentage == 100.0
        assert result.total_score == Decimal("20.00")
        assert result.readiness_level == "advanced"

    def test_all_wrong(self) -> None:
        qs = [self._make_q("q1", ms=10), self._make_q("q2", ms=10)]
        sas = [self._make_sa("q1", 0, ms=10), self._make_sa("q2", 0, ms=10)]
        result = aggregate_results(sas, qs)
        assert result.percentage == 0.0
        assert result.readiness_level == "beginner"

    def test_weighted_percentage(self) -> None:
        qs = [self._make_q("q1", ms=10), self._make_q("q2", ms=20)]
        sas = [self._make_sa("q1", 10, ms=10), self._make_sa("q2", 0, ms=20)]
        result = aggregate_results(sas, qs)
        # 10 out of 30 = 33.33%
        assert result.percentage == pytest.approx(33.33, abs=0.01)
        assert result.readiness_level == "beginner"

    def test_dimension_scoring(self) -> None:
        qs = [
            self._make_q("q1", dim="math", ms=10),
            self._make_q("q2", dim="math", ms=10),
            self._make_q("q3", dim="logic", ms=10),
        ]
        sas = [
            self._make_sa("q1", 10, ms=10),
            self._make_sa("q2", 5, ms=10),
            self._make_sa("q3", 0, ms=10),
        ]
        result = aggregate_results(sas, qs)
        assert result.dimension_scores["math"] == pytest.approx(75.0, abs=0.01)
        assert result.dimension_scores["logic"] == 0.0

    def test_readiness_level_boundaries(self) -> None:
        qs = [self._make_q("q1", ms=10)]
        # beginner (<40): 3.9/10 = 39%
        assert aggregate_results([self._make_sa("q1", 3.9, ms=10)], qs).readiness_level == "beginner"
        # intermediate (40-69): 4/10 = 40%, 6.9/10 = 69%
        assert aggregate_results([self._make_sa("q1", 4.0, ms=10)], qs).readiness_level == "intermediate"
        assert aggregate_results([self._make_sa("q1", 6.9, ms=10)], qs).readiness_level == "intermediate"
        # proficient (70-84): 7/10 = 70%, 8.4/10 = 84%
        assert aggregate_results([self._make_sa("q1", 7.0, ms=10)], qs).readiness_level == "proficient"
        assert aggregate_results([self._make_sa("q1", 8.4, ms=10)], qs).readiness_level == "proficient"
        # advanced (85+): 8.5/10 = 85%
        assert aggregate_results([self._make_sa("q1", 8.5, ms=10)], qs).readiness_level == "advanced"
        assert aggregate_results([self._make_sa("q1", 10.0, ms=10)], qs).readiness_level == "advanced"

    def test_no_questions_returns_zero(self) -> None:
        result = aggregate_results([], [])
        assert result.percentage == 0.0
        assert result.total_score == Decimal("0.00")
        assert result.readiness_level == "beginner"

    def test_empty_dimension_not_in_output(self) -> None:
        """Dimensions with no questions should not produce division by zero."""
        qs = [self._make_q("q1", dim="math", ms=10)]
        sas = [self._make_sa("q1", 5, ms=10)]
        result = aggregate_results(sas, qs)
        assert "math" in result.dimension_scores
        # A dimension with no questions should not appear
        assert len(result.dimension_scores) == 1
