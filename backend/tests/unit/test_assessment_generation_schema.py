"""Unit tests for assessment generation schema, validation, and fallback."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.workers.assessment_generation import (
    AssessmentGenerationInput,
    GeneratedAssessmentQuestion,
    validate_questions,
    _build_fallback_assessment,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_single_choice() -> GeneratedAssessmentQuestion:
    return GeneratedAssessmentQuestion(
        question_type="single_choice",
        prompt="What is the capital of France?",
        options=[
            {"value": "a", "label": "Paris"},
            {"value": "b", "label": "London"},
            {"value": "c", "label": "Berlin"},
            {"value": "d", "label": "Madrid"},
        ],
        correct_answer="a",
        explanation="Paris is the capital of France.",
        difficulty="easy",
        knowledge_point="geography",
        max_score=1,
    )


@pytest.fixture
def valid_multiple_choice() -> GeneratedAssessmentQuestion:
    return GeneratedAssessmentQuestion(
        question_type="multiple_choice",
        prompt="Which are fruits?",
        options=[
            {"value": "a", "label": "Apple"},
            {"value": "b", "label": "Banana"},
            {"value": "c", "label": "Carrot"},
            {"value": "d", "label": "Tomato"},
        ],
        correct_answer=["a", "b"],
        explanation="Apple and Banana are fruits.",
        difficulty="easy",
        knowledge_point="botany",
        max_score=2,
    )


@pytest.fixture
def valid_true_false() -> GeneratedAssessmentQuestion:
    return GeneratedAssessmentQuestion(
        question_type="true_false",
        prompt="The Earth is flat.",
        correct_answer=False,
        explanation="The Earth is spherical.",
        difficulty="easy",
        knowledge_point="science",
        max_score=1,
    )


@pytest.fixture
def valid_short_answer() -> GeneratedAssessmentQuestion:
    return GeneratedAssessmentQuestion(
        question_type="short_answer",
        prompt="Explain photosynthesis.",
        reference_answer="Photosynthesis is the process by which plants convert sunlight into energy.",
        rubric=["Correctly identifies the process (3 pts)", "Mentions energy conversion (2 pts)"],
        explanation="This tests understanding of basic biology.",
        difficulty="medium",
        knowledge_point="biology",
        max_score=5,
    )


@pytest.fixture
def fallback_ctx() -> AssessmentGenerationInput:
    return AssessmentGenerationInput(
        assessment_id="test-id",
        purpose="quiz_bank",
        node_title="Python Variables",
        learning_objectives=("Understand variable assignment", "Use different data types"),
        unit_summary="This unit covers Python variables and data types.",
        key_terms=("variable", "assignment", "type", "integer", "string"),
        common_mistakes=("Using undeclared variables", "Type confusion"),
        diagnostic_weaknesses=(),
        target_difficulty="beginner",
        question_count=8,
    )


# ---------------------------------------------------------------------------
# Schema validation: GeneratedAssessmentQuestion
# ---------------------------------------------------------------------------


class TestGeneratedAssessmentQuestion:
    """Strict schema validation for generated questions."""

    def test_extra_fields_rejected(self):
        """Extra fields in the model must raise ValidationError."""
        with pytest.raises(ValidationError):
            GeneratedAssessmentQuestion(
                question_type="single_choice",
                prompt="Test question here?",
                options=[{"value": "a", "label": "A"}, {"value": "b", "label": "B"}],
                correct_answer="a",
                explanation="Test explanation for extra field test.",
                difficulty="easy",
                knowledge_point="test",
                max_score=1,
                extra_field="should_not_exist",
            )

    def test_invalid_question_type_rejected(self):
        """Unknown question type must raise ValidationError."""
        with pytest.raises(ValidationError):
            GeneratedAssessmentQuestion(
                question_type="essay",
                prompt="Test question here?",
                explanation="Test explanation for invalid type.",
                difficulty="easy",
                knowledge_point="test",
                max_score=1,
            )

    def test_invalid_difficulty_rejected(self):
        """Invalid difficulty value must raise ValidationError."""
        with pytest.raises(ValidationError):
            GeneratedAssessmentQuestion(
                question_type="single_choice",
                prompt="Test question here?",
                options=[{"value": "a", "label": "A"}, {"value": "b", "label": "B"}],
                correct_answer="a",
                explanation="Test explanation for invalid difficulty.",
                difficulty="expert",
                knowledge_point="test",
                max_score=1,
            )

    def test_empty_prompt_rejected(self):
        """Empty prompt must raise ValidationError."""
        with pytest.raises(ValidationError):
            GeneratedAssessmentQuestion(
                question_type="single_choice",
                prompt="",
                options=[{"value": "a", "label": "A"}, {"value": "b", "label": "B"}],
                correct_answer="a",
                explanation="Test explanation for empty prompt.",
                difficulty="easy",
                knowledge_point="test",
                max_score=1,
            )

    def test_zero_max_score_rejected(self):
        """max_score must be greater than 0."""
        with pytest.raises(ValidationError):
            GeneratedAssessmentQuestion(
                question_type="single_choice",
                prompt="Test question here?",
                options=[{"value": "a", "label": "A"}, {"value": "b", "label": "B"}],
                correct_answer="a",
                explanation="Test explanation for zero max score.",
                difficulty="easy",
                knowledge_point="test",
                max_score=0,
            )

    def test_valid_single_choice(self, valid_single_choice):
        """Valid single_choice should not raise."""
        assert valid_single_choice.question_type == "single_choice"
        assert valid_single_choice.correct_answer == "a"

    def test_valid_multiple_choice(self, valid_multiple_choice):
        """Valid multiple_choice should not raise."""
        assert valid_multiple_choice.question_type == "multiple_choice"
        assert valid_multiple_choice.correct_answer == ["a", "b"]

    def test_valid_true_false(self, valid_true_false):
        """Valid true_false should not raise."""
        assert valid_true_false.question_type == "true_false"
        assert valid_true_false.correct_answer is False

    def test_valid_short_answer(self, valid_short_answer):
        """Valid short_answer should not raise."""
        assert valid_short_answer.question_type == "short_answer"
        assert valid_short_answer.correct_answer is None
        assert valid_short_answer.reference_answer is not None
        assert len(valid_short_answer.rubric) >= 1

    def test_short_answer_with_correct_answer_rejected(self):
        """Short answer must not have correct_answer — caught by validate_questions."""
        q = GeneratedAssessmentQuestion(
            question_type="short_answer",
            prompt="Test question here?",
            reference_answer="Test answer for validation.",
            rubric=["Test rubric criteria"],
            correct_answer="wrong",
            explanation="Test explanation for short answer correct_answer check.",
            difficulty="medium",
            knowledge_point="test",
            max_score=5,
        )
        errors = validate_questions([q])
        assert any("correct_answer" in e and "short_answer" in e for e in errors)


# ---------------------------------------------------------------------------
# Validation logic
# ---------------------------------------------------------------------------


class TestValidateQuestions:
    """Business rule validation."""

    def test_single_choice_answer_not_in_options(self, valid_single_choice):
        """Correct answer must be one of the option values."""
        q = GeneratedAssessmentQuestion(
            question_type="single_choice",
            prompt=valid_single_choice.prompt,
            options=valid_single_choice.options,
            correct_answer="z",
            explanation=valid_single_choice.explanation,
            difficulty=valid_single_choice.difficulty,
            knowledge_point=valid_single_choice.knowledge_point,
            max_score=valid_single_choice.max_score,
        )
        errors = validate_questions([q])
        assert any("correct_answer" in e for e in errors)

    def test_single_choice_duplicate_option_values(self, valid_single_choice):
        """Option values must be unique."""
        q = GeneratedAssessmentQuestion(
            question_type="single_choice",
            prompt=valid_single_choice.prompt,
            options=[
                {"value": "a", "label": "First"},
                {"value": "a", "label": "Second"},
            ],
            correct_answer="a",
            explanation=valid_single_choice.explanation,
            difficulty=valid_single_choice.difficulty,
            knowledge_point=valid_single_choice.knowledge_point,
            max_score=valid_single_choice.max_score,
        )
        errors = validate_questions([q])
        assert any("duplicate" in e.lower() for e in errors)

    def test_multiple_choice_answer_not_in_options(self, valid_multiple_choice):
        """Each answer must be a valid option value."""
        q = GeneratedAssessmentQuestion(
            question_type="multiple_choice",
            prompt=valid_multiple_choice.prompt,
            options=valid_multiple_choice.options,
            correct_answer=["a", "z"],
            explanation=valid_multiple_choice.explanation,
            difficulty=valid_multiple_choice.difficulty,
            knowledge_point=valid_multiple_choice.knowledge_point,
            max_score=valid_multiple_choice.max_score,
        )
        errors = validate_questions([q])
        assert any("'z'" in e for e in errors)

    def test_true_false_with_options_rejected(self):
        """True/false must not have options."""
        q = GeneratedAssessmentQuestion(
            question_type="true_false",
            prompt="Is the sky blue during daytime?",
            options=[{"value": "a", "label": "A"}, {"value": "b", "label": "B"}],
            correct_answer=True,
            explanation="The sky appears blue during daytime due to Rayleigh scattering.",
            difficulty="easy",
            knowledge_point="science",
            max_score=1,
        )
        errors = validate_questions([q])
        assert any("options" in e and "true_false" in e for e in errors)

    def test_true_false_non_bool_answer_rejected(self):
        """True/false correct_answer must be boolean."""
        q = GeneratedAssessmentQuestion(
            question_type="true_false",
            prompt="Is the sky blue?",
            correct_answer="true",
            explanation="The sky appears blue due to Rayleigh scattering.",
            difficulty="easy",
            knowledge_point="science",
            max_score=1,
        )
        errors = validate_questions([q])
        assert any("boolean" in e.lower() or "bool" in e.lower() for e in errors)

    def test_short_answer_missing_rubric(self):
        """Short answer must have rubric."""
        q = GeneratedAssessmentQuestion(
            question_type="short_answer",
            prompt="Explain gravity in simple terms.",
            reference_answer="Gravity is a force that attracts objects with mass.",
            rubric=None,
            explanation="This question tests understanding of fundamental physics.",
            difficulty="medium",
            knowledge_point="physics",
            max_score=5,
        )
        errors = validate_questions([q])
        assert any("rubric" in e.lower() for e in errors)

    def test_duplicate_prompts_rejected(self):
        """Duplicate prompts should be flagged."""
        questions = [
            GeneratedAssessmentQuestion(
                question_type="single_choice",
                prompt="What is the same question?",
                options=[{"value": "a", "label": "A"}, {"value": "b", "label": "B"}],
                correct_answer="a",
                explanation="First explanation for duplicate test.",
                difficulty="easy",
                knowledge_point="test",
                max_score=1,
            ),
            GeneratedAssessmentQuestion(
                question_type="single_choice",
                prompt="What is the same question?",
                options=[{"value": "a", "label": "X"}, {"value": "b", "label": "Y"}],
                correct_answer="a",
                explanation="Second explanation for duplicate test.",
                difficulty="easy",
                knowledge_point="test",
                max_score=1,
            ),
        ]
        errors = validate_questions(questions)
        assert any("duplicate" in e.lower() for e in errors)

    def test_single_choice_less_than_two_options_rejected(self):
        """Single choice needs at least 2 options."""
        q = GeneratedAssessmentQuestion(
            question_type="single_choice",
            prompt="Test question for minimum options validation?",
            options=[{"value": "a", "label": "Only option"}],
            correct_answer="a",
            explanation="Test explanation for min options validation.",
            difficulty="easy",
            knowledge_point="test",
            max_score=1,
        )
        errors = validate_questions([q])
        assert any("at least 2" in e.lower() for e in errors)

    def test_question_count_limit(self):
        """validate_questions should handle a large set efficiently."""
        questions = []
        for i in range(50):
            questions.append(
                GeneratedAssessmentQuestion(
                    question_type="single_choice",
                    prompt=f"Question number {i} about validation?",
                    options=[{"value": "a", "label": "A"}, {"value": "b", "label": "B"}],
                    correct_answer="a",
                    explanation=f"Test explanation for question {i} validation.",
                    difficulty="easy",
                    knowledge_point="test",
                    max_score=1,
                )
            )
        errors = validate_questions(questions)
        assert len(errors) == 0


# ---------------------------------------------------------------------------
# Fallback generation
# ---------------------------------------------------------------------------


class TestFallbackAssessment:
    """Fallback assessment generation."""

    def test_fallback_generates_correct_count(self, fallback_ctx):
        """Fallback should generate the requested question count."""
        result = _build_fallback_assessment(fallback_ctx)
        assert len(result.questions) == fallback_ctx.question_count

    def test_fallback_includes_title_and_description(self, fallback_ctx):
        """Fallback should include a title and description."""
        result = _build_fallback_assessment(fallback_ctx)
        assert result.title
        assert result.description

    def test_fallback_questions_valid(self, fallback_ctx):
        """All fallback questions should pass validation."""
        result = _build_fallback_assessment(fallback_ctx)
        errors = validate_questions(result.questions)
        assert not errors, f"Fallback questions have validation errors: {errors}"

    def test_fallback_all_question_types_present(self, fallback_ctx):
        """Fallback should generate multiple question types."""
        result = _build_fallback_assessment(fallback_ctx)
        types = {q.question_type for q in result.questions}
        assert "single_choice" in types
        assert len(types) >= 2

    def test_fallback_short_answer_has_reference(self, fallback_ctx):
        """Short answer questions in fallback should have reference_answer and rubric."""
        result = _build_fallback_assessment(fallback_ctx)
        for q in result.questions:
            if q.question_type == "short_answer":
                assert q.reference_answer, "Short answer missing reference_answer"
                assert q.rubric, "Short answer missing rubric"

    def test_fallback_true_false_is_bool(self, fallback_ctx):
        """True/false questions in fallback should have boolean correct_answer."""
        result = _build_fallback_assessment(fallback_ctx)
        for q in result.questions:
            if q.question_type == "true_false":
                assert isinstance(q.correct_answer, bool)

    def test_fallback_no_answer_leak(self, fallback_ctx):
        """Safe DTO should not include answer fields."""
        result = _build_fallback_assessment(fallback_ctx)
        for q in result.questions:
            dto = {
                "question_id": "test",
                "type": q.question_type,
                "prompt": q.prompt,
            }
            assert "correct_answer" not in dto
            assert "reference_answer" not in dto
            assert "rubric" not in dto

    def test_fallback_quiz_bank_has_8_questions(self):
        """Quiz bank should generate 8 questions."""
        ctx = AssessmentGenerationInput(
            assessment_id="test",
            purpose="quiz_bank",
            node_title="Test",
            learning_objectives=("Obj 1",),
            unit_summary="",
            key_terms=(),
            common_mistakes=(),
            diagnostic_weaknesses=(),
            target_difficulty="beginner",
            question_count=8,
        )
        result = _build_fallback_assessment(ctx)
        assert len(result.questions) == 8

    def test_fallback_formal_has_10_questions(self):
        """Formal assessment should generate 10 questions."""
        ctx = AssessmentGenerationInput(
            assessment_id="test",
            purpose="formal",
            node_title="Test",
            learning_objectives=("Obj 1",),
            unit_summary="",
            key_terms=(),
            common_mistakes=(),
            diagnostic_weaknesses=(),
            target_difficulty="intermediate",
            question_count=10,
        )
        result = _build_fallback_assessment(ctx)
        assert len(result.questions) == 10

    def test_fallback_without_objectives(self):
        """Fallback works even without learning objectives."""
        ctx = AssessmentGenerationInput(
            assessment_id="test",
            purpose="practice",
            node_title="Test Only",
            learning_objectives=(),
            unit_summary="",
            key_terms=(),
            common_mistakes=(),
            diagnostic_weaknesses=(),
            target_difficulty="advanced",
            question_count=5,
        )
        result = _build_fallback_assessment(ctx)
        assert len(result.questions) == 5
        assert result.title
