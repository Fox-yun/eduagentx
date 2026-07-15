"""Unit tests for strict full-flow smoke-test helpers."""

from scripts.smoke_full_learning_flow import _build_smoke_answers, _select_smoke_answer

from app.workers.assessment_generation import AssessmentGenerationInput, _build_fallback_assessment


def test_selects_semantically_correct_fallback_answers() -> None:
    questions = [
        {
            "question_id": "single",
            "type": "single_choice",
            "prompt": "以下哪种做法最有效？",
            "options": [
                {"value": "a", "label": "只看不练，追求速度"},
                {"value": "b", "label": "先理解原理，再结合实际场景实践"},
            ],
        },
        {
            "question_id": "multiple",
            "type": "multiple_choice",
            "prompt": "哪些是良好实践？",
            "options": [
                {"value": "a", "label": "编写清晰的文档和注释"},
                {"value": "b", "label": "遵循规范和最佳实践"},
                {"value": "c", "label": "进行充分的测试"},
                {"value": "d", "label": "忽略性能和可维护性"},
            ],
        },
        {
            "question_id": "objective",
            "type": "single_choice",
            "prompt": "学习本单元的首要目标是什么？",
            "options": [
                {"value": "a", "label": "记忆所有相关定义和术语"},
                {"value": "b", "label": "能够在本地运行 Python 脚本"},
                {"value": "c", "label": "跳过基础直接学习高级内容"},
            ],
        },
        {
            "question_id": "boolean",
            "type": "true_false",
            "prompt": "学习只需要理论知识，不需要动手实践。",
        },
    ]

    assert _build_smoke_answers(questions) == {
        "single": "b",
        "multiple": ["a", "b", "c"],
        "objective": "b",
        "boolean": False,
    }


def test_short_answer_is_substantive() -> None:
    answer = _select_smoke_answer(
        {"question_id": "short", "type": "short_answer", "prompt": "说明概念与应用"}
    )

    assert isinstance(answer, str)
    assert len(answer) >= 80
    assert "实际开发" in answer


def test_smoke_answers_pass_the_formal_fallback_assessment() -> None:
    assessment = _build_fallback_assessment(
        AssessmentGenerationInput(
            assessment_id="assessment",
            purpose="formal",
            node_title="Python 基础",
            learning_objectives=("能够在本地运行 Python 脚本", "编写控制台交互程序"),
            unit_summary="",
            key_terms=(),
            common_mistakes=(),
            diagnostic_weaknesses=(),
            target_difficulty="beginner",
            question_count=10,
        )
    )
    public_questions = [
        {
            "question_id": str(index),
            "type": question.question_type,
            "prompt": question.prompt,
            "options": [option.model_dump() for option in question.options] if question.options else None,
        }
        for index, question in enumerate(assessment.questions)
    ]

    answers = _build_smoke_answers(public_questions)

    for index, question in enumerate(assessment.questions):
        assert answers[str(index)] == question.correct_answer
