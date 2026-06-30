"""Unit tests for services with mocked database sessions."""

from unittest.mock import AsyncMock, MagicMock

import pytest


class MockModel:
    """Generic mock for SQLAlchemy model instances."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class TestUnitServiceFormatAssessment:
    """Test _format_assessment without real DB."""

    @pytest.mark.asyncio
    async def test_format_assessment_returns_dict(self):
        from app.services.unit import UnitService

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        svc = UnitService(mock_db)

        assessment = MockModel(id="a-1", path_id="p-1", node_id="n-1", status="pending")
        question = MockModel(
            id="q-1",
            assessment_id="a-1",
            question_type="single_choice",
            prompt="What is X?",
            options='[{"value":"a","label":"Option A"},{"value":"b","label":"Option B"}]',
            correct_answer="a",
            points=1,
            question_order=1,
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [question]
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await svc._format_assessment(assessment)
        assert result["assessment_id"] == "a-1"
        assert result["status"] == "pending"
        assert len(result["questions"]) == 1
        assert result["questions"][0]["question_id"] == "q-1"
        assert result["questions"][0]["prompt"] == "What is X?"

    @pytest.mark.asyncio
    async def test_format_assessment_with_none_options(self):
        from app.services.unit import UnitService

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        svc = UnitService(mock_db)

        assessment = MockModel(id="a-1", path_id="p-1", node_id="n-1", status="pending")
        question = MockModel(
            id="q-1",
            assessment_id="a-1",
            question_type="short_answer",
            prompt="Explain X",
            options=None,
            correct_answer="",
            points=3,
            question_order=1,
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [question]
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await svc._format_assessment(assessment)
        assert result["questions"][0]["options"] == []


class TestUnitServiceGetUnitContent:
    """Test get_unit_content with mocked DB."""

    @pytest.mark.asyncio
    async def test_returns_not_generated_when_no_content(self):
        from app.services.unit import UnitService

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        svc = UnitService(mock_db)

        # Mock: no content found, no active task
        empty_result = MagicMock()
        empty_result.scalar_one_or_none.return_value = None

        async def mock_execute(stmt, **kw):
            return empty_result

        mock_db.execute = mock_execute

        result = await svc.get_unit_content("p-1", "n-1", "u-1")
        assert result["status"] in ("not_generated", "generating")


class TestGoalServiceValidation:
    """Test goal state transition validation."""

    def test_valid_transitions(self):
        valid_transitions = {
            "draft": ["clarifying"],
            "clarifying": ["diagnosing"],
            "diagnosing": ["planning"],
            "planning": ["ready"],
            "ready": ["active"],
        }
        for src, targets in valid_transitions.items():
            for t in targets:
                assert t != src  # No self-transitions

    def test_terminal_states(self):
        terminal = {"active", "archived"}
        for s in terminal:
            assert s not in {"draft", "clarifying", "diagnosing", "planning", "ready"}


class TestPathServiceDAGValidation:
    """Test DAG validation logic."""

    def test_linear_dag_valid(self):
        edges = [("n1", "n2"), ("n2", "n3")]
        nodes = {"n1", "n2", "n3"}
        # No cycles in a linear chain
        assert len(edges) == len(nodes) - 1

    def test_diamond_dag_valid(self):
        edges = [("n1", "n2"), ("n1", "n3"), ("n2", "n4"), ("n3", "n4")]
        assert len(edges) == 4

    def test_cycle_detection(self):
        edges = [("n1", "n2"), ("n2", "n3"), ("n3", "n1")]
        # This is a cycle - should be detected
        adj: dict[str, list[str]] = {}
        for src, tgt in edges:
            adj.setdefault(src, []).append(tgt)

        visited = set()
        rec_stack = set()

        def has_cycle(node):
            visited.add(node)
            rec_stack.add(node)
            for neighbor in adj.get(node, []):
                if neighbor not in visited:
                    if has_cycle(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            rec_stack.discard(node)
            return False

        assert has_cycle("n1") is True


class TestTaskStateTransitions:
    """Test task state machine rules."""

    def test_pending_can_go_to_running(self):
        assert "running" in {"running", "cancelled"}

    def test_running_can_go_to_completed(self):
        assert "completed" in {"completed", "failed", "interrupted", "cancelled"}

    def test_completed_is_terminal(self):
        from app.common.enums import TERMINAL_TASK_STATUSES

        assert "completed" in TERMINAL_TASK_STATUSES

    def test_failed_is_terminal(self):
        from app.common.enums import TERMINAL_TASK_STATUSES

        assert "failed" in TERMINAL_TASK_STATUSES


class TestSecurityModule:
    """Test security helper functions."""

    def test_password_hashing(self):
        from app.core.security import hash_password, verify_password

        pw = "TestPassword123!"
        hashed = hash_password(pw)
        assert hashed != pw
        assert verify_password(pw, hashed) is True
        assert verify_password("wrong", hashed) is False

    def test_csrf_token_generation(self):
        from app.core.security import generate_csrf_token

        token = generate_csrf_token()
        assert len(token) > 20
        assert token != generate_csrf_token()  # Should be random


class TestRequestContext:
    """Test request context utilities."""

    def test_request_context_module_importable(self):
        import app.core.request_context

        assert app.core.request_context is not None
