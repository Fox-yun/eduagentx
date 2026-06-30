"""Comprehensive unit tests for UnitService."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.errors import ApiError


def _mock_scalar_result(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _mock_scalars(items):
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


def _mock_scalar(value):
    r = MagicMock()
    r.scalar.return_value = value
    return r


def _make_content(**overrides):
    c = MagicMock()
    c.id = overrides.get("id", "content-1")
    c.path_id = overrides.get("path_id", "path-1")
    c.node_id = overrides.get("node_id", "node-1")
    c.user_id = overrides.get("user_id", "user-1")
    c.version_number = overrides.get("version_number", 1)
    c.status = overrides.get("status", "ready")
    c.content = overrides.get(
        "content",
        {
            "introduction": "Intro",
            "objectives": ["Obj1"],
            "sections": [{"title": "Sec1", "content": "Content1"}],
            "practice_tasks": [],
            "summary": "Summary",
            "references": [],
        },
    )
    return c


def _make_assessment(**overrides):
    a = MagicMock()
    a.id = overrides.get("id", "assess-1")
    a.user_id = overrides.get("user_id", "user-1")
    a.path_id = overrides.get("path_id", "path-1")
    a.path_version_id = overrides.get("path_version_id", "")
    a.node_id = overrides.get("node_id", "node-1")
    a.status = overrides.get("status", "pending")
    return a


def _make_question(**overrides):
    q = MagicMock()
    q.id = overrides.get("id", "q-1")
    q.assessment_id = overrides.get("assessment_id", "assess-1")
    q.question_type = overrides.get("question_type", "single_choice")
    q.prompt = overrides.get("prompt", "What is X?")
    q.options = overrides.get("options", json.dumps([{"value": "a", "label": "A"}, {"value": "b", "label": "B"}]))
    q.correct_answer = overrides.get("correct_answer", "a")
    q.points = overrides.get("points", 1)
    q.question_order = overrides.get("question_order", 1)
    return q


def _make_node(**overrides):
    n = MagicMock()
    n.id = overrides.get("id", "node-1")
    n.title = overrides.get("title", "Test Node")
    n.learning_outcomes = overrides.get("learning_outcomes", '["outcome1"]')
    return n


class TestUnitServiceGetUnitContent:
    @pytest.mark.asyncio
    async def test_get_existing_content(self):
        from app.services.unit import UnitService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = UnitService(db)
        content = _make_content()
        db.execute = AsyncMock(return_value=_mock_scalar_result(content))

        result = await svc.get_unit_content("path-1", "node-1", "user-1")
        assert result["unit_id"] == "content-1"
        assert result["status"] == "ready"
        assert result["introduction"] == "Intro"

    @pytest.mark.asyncio
    async def test_get_no_content_no_task(self):
        from app.services.unit import UnitService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = UnitService(db)

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(None)  # no content
            elif call_count == 2:
                return _mock_scalar_result(None)  # no task
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await svc.get_unit_content("path-1", "node-1", "user-1")
        assert result["status"] == "not_generated"
        assert result["active_task_id"] is None

    @pytest.mark.asyncio
    async def test_get_no_content_with_active_task(self):
        from app.services.unit import UnitService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = UnitService(db)

        task = MagicMock()
        task.id = "task-1"

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(None)
            elif call_count == 2:
                return _mock_scalar_result(task)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await svc.get_unit_content("path-1", "node-1", "user-1")
        assert result["status"] == "generating"
        assert result["active_task_id"] == "task-1"


class TestUnitServiceCreateAssessment:
    @pytest.mark.asyncio
    async def test_create_new_assessment(self):
        from app.services.unit import UnitService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = UnitService(db)

        questions = [
            {
                "type": "single_choice",
                "prompt": f"Q{i}",
                "options": [{"value": "a", "label": "A"}],
                "correct_answer": "a",
                "points": 1,
            }
            for i in range(12)
        ]

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # existing assessment check
                return _mock_scalar_result(None)
            elif call_count == 2:  # node lookup
                return _mock_scalar_result(_make_node())
            elif call_count == 3:  # format: get questions
                return _mock_scalars([])
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with patch.object(svc, "_llm_generate_questions", new_callable=AsyncMock, return_value=questions):
            result = await svc.create_assessment("path-1", "node-1", "user-1")
            assert "assessment_id" in result
            assert result["status"] == "pending"

    @pytest.mark.asyncio
    async def test_create_assessment_existing(self):
        from app.services.unit import UnitService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = UnitService(db)
        existing = _make_assessment()
        question = _make_question()

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(existing)  # found existing
            elif call_count == 2:
                return _mock_scalars([question])
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await svc.create_assessment("path-1", "node-1", "user-1")
        assert result["assessment_id"] == "assess-1"


class TestUnitServiceCreatePractice:
    @pytest.mark.asyncio
    async def test_create_practice(self):
        from app.services.unit import UnitService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = UnitService(db)

        questions = [
            {"type": "single_choice", "prompt": "Q1", "options": [{"value": "a", "label": "A"}], "correct_answer": "a"},
        ]

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(_make_node())
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with patch.object(svc, "_llm_generate_questions", new_callable=AsyncMock, return_value=questions):
            result = await svc.create_practice("path-1", "node-1", "user-1")
            assert result["node_id"] == "node-1"
            assert len(result["questions"]) == 1

    @pytest.mark.asyncio
    async def test_create_practice_no_node(self):
        from app.services.unit import UnitService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = UnitService(db)

        questions = [
            {"type": "single_choice", "prompt": "Q1", "correct_answer": "a"},
        ]

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(None)  # no node
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with patch.object(svc, "_llm_generate_questions", new_callable=AsyncMock, return_value=questions):
            result = await svc.create_practice("path-1", "bad-node", "user-1")
            assert result["node_id"] == "bad-node"


class TestUnitServiceTemplateQuestions:
    def test_generate_assessment_questions_with_outcomes(self):
        from app.services.unit import UnitService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = UnitService(db)
        questions = svc._generate_assessment_questions("Python Lists", ["Create lists", "Use list methods"])
        assert len(questions) == 12
        types = [q["type"] for q in questions]
        assert types.count("single_choice") >= 6
        assert types.count("multiple_choice") >= 2
        assert types.count("short_answer") >= 2

    def test_generate_assessment_questions_no_outcomes(self):
        from app.services.unit import UnitService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = UnitService(db)
        questions = svc._generate_assessment_questions("Test Topic", [])
        assert len(questions) == 12

    def test_generate_practice_questions(self):
        from app.services.unit import UnitService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = UnitService(db)
        questions = svc._generate_practice_questions("Test Topic", ["Outcome 1"])
        assert len(questions) == 5
        types = [q["type"] for q in questions]
        assert "single_choice" in types
        assert "multiple_choice" in types
        assert "short_answer" in types


class TestUnitServiceSubmitAssessment:
    @pytest.mark.asyncio
    async def test_submit_not_found(self):
        from app.services.unit import UnitService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = UnitService(db)
        db.execute = AsyncMock(return_value=_mock_scalar_result(None))

        with pytest.raises(ApiError) as exc_info:
            await svc.submit_assessment("bad-id", "user-1", {})
        assert exc_info.value.code == "ASSESSMENT_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_submit_pass_with_all_correct(self):
        from app.services.unit import UnitService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = UnitService(db)

        assessment = _make_assessment()
        node = _make_node()
        q1 = _make_question(id="q1", question_type="single_choice", correct_answer="a", points=1)
        q2 = _make_question(id="q2", question_type="single_choice", correct_answer="b", points=1)

        progress = MagicMock()
        progress.mastery = 50.0
        progress.status = "in_progress"
        progress.attempts = 0

        profile = MagicMock()
        profile.learning_dimensions = {
            "knowledge_depth": 50,
            "practice_ability": 50,
            "learning_efficiency": 50,
            "concept_grasp": 50,
            "problem_solving": 50,
        }

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # assessment
                return _mock_scalar_result(assessment)
            elif call_count == 2:  # node
                return _mock_scalar_result(node)
            elif call_count == 3:  # questions
                return _mock_scalars([q1, q2])
            elif call_count == 4:  # mastery progress
                return _mock_scalar_result(progress)
            elif call_count == 5:  # unlock: get path
                return _mock_scalar_result(None)
            elif call_count == 6:  # update_progress: get progress
                return _mock_scalar_result(progress)
            elif call_count == 7:  # profile service: get profile
                return _mock_scalar_result(profile)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with patch("app.services.llm.llm_json", new_callable=AsyncMock, side_effect=Exception("skip")):
            result = await svc.submit_assessment("assess-1", "user-1", {"q1": "a", "q2": "b"})
            assert result["score"] == 100.0
            assert result["passed"] is True

    @pytest.mark.asyncio
    async def test_submit_fail_with_wrong_answers(self):
        from app.services.unit import UnitService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = UnitService(db)

        assessment = _make_assessment()
        node = _make_node()
        q1 = _make_question(id="q1", question_type="single_choice", correct_answer="a", points=5)

        progress = MagicMock()
        progress.mastery = 50.0

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(assessment)
            elif call_count == 2:
                return _mock_scalar_result(node)
            elif call_count == 3:
                return _mock_scalars([q1])
            elif call_count == 4:  # mastery
                return _mock_scalar_result(progress)
            elif call_count == 5:  # _unlock_next_nodes: path
                return _mock_scalar_result(None)
            elif call_count == 6:  # _update_progress: progress
                return _mock_scalar_result(progress)
            elif call_count == 7:  # remedial feedback: node
                return _mock_scalar_result(node)
            elif call_count == 8:  # profile: profile
                return _mock_scalar_result(None)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with patch("app.services.llm.llm_json", new_callable=AsyncMock, side_effect=Exception("skip")):
            result = await svc.submit_assessment("assess-1", "user-1", {"q1": "b"})
            assert result["score"] == 0.0
            assert result["passed"] is False

    @pytest.mark.asyncio
    async def test_submit_multiple_choice(self):
        from app.services.unit import UnitService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = UnitService(db)

        assessment = _make_assessment()
        node = _make_node()
        q1 = _make_question(
            id="q1",
            question_type="multiple_choice",
            correct_answer=json.dumps(["a", "b", "c"]),
            points=2,
        )

        progress = MagicMock()
        progress.mastery = 50.0

        profile = MagicMock()
        profile.learning_dimensions = {
            "knowledge_depth": 50,
            "practice_ability": 50,
            "learning_efficiency": 50,
            "concept_grasp": 50,
            "problem_solving": 50,
        }

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(assessment)
            elif call_count == 2:
                return _mock_scalar_result(node)
            elif call_count == 3:
                return _mock_scalars([q1])
            elif call_count == 4:
                return _mock_scalar_result(progress)
            elif call_count == 5:
                return _mock_scalar_result(None)
            elif call_count == 6:
                return _mock_scalar_result(progress)
            elif call_count == 7:
                return _mock_scalar_result(profile)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with patch("app.services.llm.llm_json", new_callable=AsyncMock, side_effect=Exception("skip")):
            result = await svc.submit_assessment("assess-1", "user-1", {"q1": ["a", "b", "c"]})
            assert result["score"] == 100.0
            assert result["passed"] is True

    @pytest.mark.asyncio
    async def test_submit_with_short_answer(self):
        from app.services.unit import UnitService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = UnitService(db)

        assessment = _make_assessment()
        node = _make_node()
        q1 = _make_question(id="q1", question_type="short_answer", correct_answer="", points=3)

        progress = MagicMock()
        progress.mastery = 50.0

        profile = MagicMock()
        profile.learning_dimensions = {
            "knowledge_depth": 50,
            "practice_ability": 50,
            "learning_efficiency": 50,
            "concept_grasp": 50,
            "problem_solving": 50,
        }

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_result(assessment)
            elif call_count == 2:
                return _mock_scalar_result(node)
            elif call_count == 3:
                return _mock_scalars([q1])
            elif call_count == 4:
                return _mock_scalar_result(progress)
            elif call_count == 5:
                return _mock_scalar_result(None)
            elif call_count == 6:
                return _mock_scalar_result(progress)
            elif call_count == 7:
                return _mock_scalar_result(profile)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        with patch("app.services.llm.llm_json", new_callable=AsyncMock, side_effect=Exception("skip")):
            result = await svc.submit_assessment("assess-1", "user-1", {"q1": "My answer"})
            assert result["score"] >= 0


class TestUnitServiceGradeShortAnswers:
    @pytest.mark.asyncio
    async def test_grade_short_answers_llm_success(self):
        from app.services.unit import UnitService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = UnitService(db)

        llm_result = {
            "grades": [
                {"index": 0, "score": 80, "feedback": "Good answer"},
                {"index": 1, "score": 40, "feedback": "Needs improvement"},
            ]
        }

        with patch("app.services.llm.llm_json", new_callable=AsyncMock, return_value=llm_result):
            result = await svc._grade_short_answers(
                [(0, "Q1?", "A1"), (1, "Q2?", "A2")],
                "Test Node",
            )
            assert result[0]["score"] == 80
            assert result[1]["score"] == 40

    @pytest.mark.asyncio
    async def test_grade_short_answers_llm_error(self):
        from app.services.unit import UnitService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = UnitService(db)

        with patch("app.services.llm.llm_json", new_callable=AsyncMock, side_effect=Exception("LLM down")):
            result = await svc._grade_short_answers(
                [(0, "Q1?", "A1")],
                "Test Node",
            )
            assert result[0]["score"] == 50
            assert "临时评分" in result[0]["feedback"]
            assert result[0]["grading_status"] == "provisional"


class TestUnitServiceFormatAssessment:
    @pytest.mark.asyncio
    async def test_format_assessment(self):
        from app.services.unit import UnitService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = UnitService(db)
        assessment = _make_assessment()
        question = _make_question()

        db.execute = AsyncMock(return_value=_mock_scalars([question]))

        result = await svc._format_assessment(assessment)
        assert result["assessment_id"] == "assess-1"
        assert len(result["questions"]) == 1
        assert result["score"] is None
        assert result["passed"] is None


class TestUnitServiceUpdateMastery:
    @pytest.mark.asyncio
    async def test_update_mastery_with_existing_progress(self):
        from app.services.unit import UnitService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = UnitService(db)
        progress = MagicMock()
        progress.mastery = 50.0

        db.execute = AsyncMock(return_value=_mock_scalar_result(progress))

        await svc._update_mastery("user-1", "node-1", 80.0, True, "assess-1")
        # new_mastery = min(100, 50 + (80 - 50) * 0.5) = min(100, 65) = 65
        assert progress.mastery == 65.0

    @pytest.mark.asyncio
    async def test_update_mastery_no_existing_progress(self):
        from app.services.unit import UnitService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = UnitService(db)
        db.execute = AsyncMock(return_value=_mock_scalar_result(None))

        await svc._update_mastery("user-1", "node-1", 80.0, True, "assess-1")
        # No progress record, so no update but snapshot still created
        assert db.add.called


class TestUnitServiceUnlockNextNodes:
    @pytest.mark.asyncio
    async def test_unlock_when_all_prereqs_met(self):
        from app.services.unit import UnitService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = UnitService(db)

        path = MagicMock()
        path.active_version_id = "ver-1"

        edge = MagicMock()
        edge.target_node_id = "node-2"
        edge.source_node_id = "node-1"

        prereq_progress = MagicMock()
        prereq_progress.status = "completed"

        target_progress = MagicMock()
        target_progress.status = "locked"

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # path
                return _mock_scalar_result(path)
            elif call_count == 2 or call_count == 3:  # outgoing edges
                return _mock_scalars([edge])
            elif call_count == 4:  # prereq progress
                return _mock_scalar_result(prereq_progress)
            elif call_count == 5:  # target progress
                return _mock_scalar_result(target_progress)
            return _mock_scalar_result(None)

        db.execute = AsyncMock(side_effect=execute_side_effect)

        await svc._unlock_next_nodes("user-1", "path-1", "node-1")
        assert target_progress.status == "available"

    @pytest.mark.asyncio
    async def test_unlock_no_path(self):
        from app.services.unit import UnitService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = UnitService(db)
        db.execute = AsyncMock(return_value=_mock_scalar_result(None))

        # Should not raise
        await svc._unlock_next_nodes("user-1", "path-1", "node-1")
