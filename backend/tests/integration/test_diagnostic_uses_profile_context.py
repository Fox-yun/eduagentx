"""Integration tests: Diagnostic uses learner profile context.

Verifies:
  - _generate_diagnostic_questions adjusts questions when profile exists
  - Weak knowledge_depth → questions marked with 【基础题】
  - Strong knowledge_depth → questions marked with 【综合题】
  - Slow learning_pace → short_answer questions get step-by-step hint
  - No profile → default question generation (no modifications)

Run with:
    pytest tests/integration/test_diagnostic_uses_profile_context.py -v
"""

from __future__ import annotations

from types import SimpleNamespace

from app.routers.diagnostics import _generate_diagnostic_questions
from app.services.profile_context import LearnerProfileContext, ProfileDimensionValue


def _make_goal(goal_id: str = "abc12345-test") -> SimpleNamespace:
    """Create a minimal goal mock for programming topic detection."""
    return SimpleNamespace(
        id=goal_id,
        raw_description="我想学习 Python 编程",
        normalized_goal="python programming",
    )


def _make_profile_context(
    knowledge_depth: float | None = None,
    learning_pace: str | None = None,
) -> LearnerProfileContext:
    """Build a LearnerProfileContext with specified dimensions."""
    dimensions: dict[str, ProfileDimensionValue] = {}
    if knowledge_depth is not None:
        dimensions["knowledge_depth"] = ProfileDimensionValue(value=knowledge_depth, confidence=0.8, source="test")
    if learning_pace is not None:
        dimensions["learning_pace"] = ProfileDimensionValue(value=learning_pace, confidence=0.7, source="test")
    return LearnerProfileContext(
        user_id="test-user",
        dimensions=dimensions,
        confidence=0.7,
        summary="test summary",
        evidence_summary=(),
        profile_version=1,
        status="active",
    )


def _is_topic_question(q: dict) -> bool:
    """Check if a question is from the programming topic bank (not general)."""
    # General questions have dimension 'self_assessment'
    # Programming questions have dimensions like 'algorithms', 'programming_fundamentals'
    return q.get("dimension") != "self_assessment"


class TestDiagnosticUsesProfileContext:
    """Verify diagnostic question generation is personalised by profile."""

    def test_no_profile_returns_default_questions(self):
        """Without a profile, questions should have no prefix markers."""
        goal = _make_goal()
        questions = _generate_diagnostic_questions(goal, profile_context=None)

        assert len(questions) > 0
        for q in questions:
            assert "【基础题】" not in q["prompt"]
            assert "【综合题】" not in q["prompt"]

    def test_weak_knowledge_depth_adds_basic_marker(self):
        """knowledge_depth < 0.4 should mark topic questions as 基础题."""
        goal = _make_goal()
        ctx = _make_profile_context(knowledge_depth=0.2)
        questions = _generate_diagnostic_questions(goal, profile_context=ctx)

        # Topic-specific questions should have the marker
        topic_questions = [q for q in questions if _is_topic_question(q)]
        # General questions should NOT have the marker
        general_questions = [q for q in questions if not _is_topic_question(q)]

        assert len(topic_questions) > 0
        for q in topic_questions:
            assert "【基础题】" in q["prompt"]
        for q in general_questions:
            assert "【基础题】" not in q["prompt"]

    def test_strong_knowledge_depth_adds_comprehensive_marker(self):
        """knowledge_depth > 0.7 should mark topic questions as 综合题."""
        goal = _make_goal()
        ctx = _make_profile_context(knowledge_depth=0.8)
        questions = _generate_diagnostic_questions(goal, profile_context=ctx)

        topic_questions = [q for q in questions if _is_topic_question(q)]

        assert len(topic_questions) > 0
        for q in topic_questions:
            assert "【综合题】" in q["prompt"]

    def test_moderate_knowledge_depth_no_marker(self):
        """0.4 <= knowledge_depth <= 0.7 should not add markers."""
        goal = _make_goal()
        ctx = _make_profile_context(knowledge_depth=0.5)
        questions = _generate_diagnostic_questions(goal, profile_context=ctx)

        for q in questions:
            assert "【基础题】" not in q["prompt"]
            assert "【综合题】" not in q["prompt"]

    def test_slow_pace_adds_step_by_step_hint(self):
        """learning_pace == 'slow' should add step-by-step hint to short_answer."""
        goal = _make_goal()
        ctx = _make_profile_context(knowledge_depth=0.5, learning_pace="slow")
        questions = _generate_diagnostic_questions(goal, profile_context=ctx)

        short_answer_questions = [q for q in questions if q.get("type") == "short_answer"]
        assert len(short_answer_questions) > 0
        for q in short_answer_questions:
            assert "分步骤" in q["prompt"] or "逐步" in q["prompt"]

    def test_fast_pace_no_step_by_step_hint(self):
        """learning_pace != 'slow' should NOT add step-by-step hint."""
        goal = _make_goal()
        ctx = _make_profile_context(knowledge_depth=0.5, learning_pace="fast")
        questions = _generate_diagnostic_questions(goal, profile_context=ctx)

        short_answer_questions = [q for q in questions if q.get("type") == "short_answer"]
        for q in short_answer_questions:
            assert "分步骤" not in q["prompt"]

    def test_questions_include_topic_and_general(self):
        """Both topic-specific and general questions should be present."""
        goal = _make_goal()
        questions = _generate_diagnostic_questions(goal, profile_context=None)

        topic_qs = [q for q in questions if _is_topic_question(q)]
        general_qs = [q for q in questions if not _is_topic_question(q)]

        assert len(topic_qs) > 0
        assert len(general_qs) > 0
