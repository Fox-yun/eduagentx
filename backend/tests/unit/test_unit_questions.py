"""Comprehensive unit tests for unit service question generation."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestUnitServiceQuestionGeneration:
    """Test _generate_assessment_questions and _generate_practice_questions."""

    def test_assessment_questions_count(self):
        from app.services.unit import UnitService

        svc = UnitService.__new__(UnitService)
        questions = svc._generate_assessment_questions("Python 列表", ["掌握列表操作", "理解列表推导式"])
        assert len(questions) >= 10

    def test_assessment_questions_types(self):
        from app.services.unit import UnitService

        svc = UnitService.__new__(UnitService)
        questions = svc._generate_assessment_questions("DFS", ["理解DFS"])
        types = {q["type"] for q in questions}
        assert "single_choice" in types
        assert "multiple_choice" in types
        assert "short_answer" in types

    def test_assessment_questions_have_prompts(self):
        from app.services.unit import UnitService

        svc = UnitService.__new__(UnitService)
        questions = svc._generate_assessment_questions("二叉树遍历", ["前序遍历"])
        for q in questions:
            assert "prompt" in q
            assert len(q["prompt"]) > 10

    def test_assessment_questions_have_correct_answers(self):
        from app.services.unit import UnitService

        svc = UnitService.__new__(UnitService)
        questions = svc._generate_assessment_questions("算法", ["排序"])
        for q in questions:
            if q["type"] in ("single_choice", "multiple_choice"):
                assert "correct_answer" in q
                assert q["correct_answer"]  # not empty

    def test_practice_questions_count(self):
        from app.services.unit import UnitService

        svc = UnitService.__new__(UnitService)
        questions = svc._generate_practice_questions("Python", ["基础"])
        assert len(questions) == 5

    def test_practice_questions_types(self):
        from app.services.unit import UnitService

        svc = UnitService.__new__(UnitService)
        questions = svc._generate_practice_questions("DFS", ["遍历"])
        types = {q["type"] for q in questions}
        assert "single_choice" in types

    def test_questions_contain_title(self):
        from app.services.unit import UnitService

        svc = UnitService.__new__(UnitService)
        title = "Python 装饰器"
        questions = svc._generate_assessment_questions(title, [])
        prompts_text = " ".join(q["prompt"] for q in questions)
        assert title in prompts_text


class TestUnitServiceFormatAssessment:
    @pytest.mark.asyncio
    async def test_format_returns_correct_structure(self):
        from app.services.unit import UnitService

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        svc = UnitService(mock_db)

        assessment = MagicMock()
        assessment.id = "a-1"
        assessment.path_id = "p-1"
        assessment.node_id = "n-1"
        assessment.status = "pending"

        question = MagicMock()
        question.id = "q-1"
        question.assessment_id = "a-1"
        question.question_type = "single_choice"
        question.prompt = "What is X?"
        question.options = json.dumps([{"value": "a", "label": "A"}, {"value": "b", "label": "B"}])
        question.correct_answer = "a"
        question.points = 1
        question.question_order = 1

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [question]
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await svc._format_assessment(assessment)
        assert result["assessment_id"] == "a-1"
        assert result["status"] == "pending"
        assert len(result["questions"]) == 1
        assert result["questions"][0]["type"] == "single_choice"


class TestUnitServiceLLMGenerateQuestions:
    @pytest.mark.asyncio
    async def test_llm_generate_falls_back_to_template(self):
        from app.services.unit import UnitService

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        svc = UnitService(mock_db)

        with patch("app.services.llm.llm_json", side_effect=Exception("LLM unavailable")):
            result = await svc._llm_generate_questions("Python", ["基础"], is_assessment=True)
            assert len(result) >= 10
            assert all("prompt" in q for q in result)
