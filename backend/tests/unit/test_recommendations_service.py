"""Unit tests for RecommendationService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.recommendations import RecommendationService


def _make_node(**overrides: object) -> MagicMock:
    n = MagicMock()
    n.id = overrides.get("id", "node-1")
    n.version_id = overrides.get("version_id", "ver-1")
    n.title = overrides.get("title", "Test Node")
    n.node_order = overrides.get("node_order", 1)
    n.level = overrides.get("level", 1)
    n.difficulty = overrides.get("difficulty", "beginner")
    n.estimated_minutes = overrides.get("estimated_minutes", 30)
    n.status = overrides.get("status", "locked")
    n.mastery = overrides.get("mastery", 0.0)
    return n


class TestRecommendationService:
    @pytest.mark.asyncio
    async def test_no_path_returns_empty(self):
        db = AsyncMock()
        svc = RecommendationService(db)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        result = await svc.get_recommendations("path-1", "user-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_no_active_version_returns_empty(self):
        db = AsyncMock()
        svc = RecommendationService(db)

        mock_path = MagicMock()
        mock_path.active_version_id = None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_path
        db.execute = AsyncMock(return_value=mock_result)

        result = await svc.get_recommendations("path-1", "user-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_continue_recommendation(self):
        db = AsyncMock()
        svc = RecommendationService(db)

        mock_path = MagicMock()
        mock_path.active_version_id = "ver-1"

        path_result = MagicMock()
        path_result.scalar_one_or_none.return_value = mock_path

        nodes = [
            _make_node(id="n1", status="completed", mastery=100.0, node_order=1),
            _make_node(id="n2", status="available", mastery=0.0, node_order=2, title="Next Topic"),
        ]

        nodes_result = MagicMock()
        nodes_result.scalars.return_value.all.return_value = nodes

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return path_result
            elif call_count == 2:
                return nodes_result
            return MagicMock()

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await svc.get_recommendations("path-1", "user-1")

        # Should have at least a continue recommendation
        continue_recs = [r for r in result if r["type"] == "continue"]
        assert len(continue_recs) == 1
        assert "Next Topic" in continue_recs[0]["title"]
        assert continue_recs[0]["node_ids"] == ["n2"]

    @pytest.mark.asyncio
    async def test_review_recommendation_low_mastery(self):
        db = AsyncMock()
        svc = RecommendationService(db)

        mock_path = MagicMock()
        mock_path.active_version_id = "ver-1"

        path_result = MagicMock()
        path_result.scalar_one_or_none.return_value = mock_path

        nodes = [
            _make_node(id="n1", status="completed", mastery=40.0, node_order=1, title="Weak Topic"),
        ]

        nodes_result = MagicMock()
        nodes_result.scalars.return_value.all.return_value = nodes

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return path_result
            elif call_count == 2:
                return nodes_result
            return MagicMock()

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await svc.get_recommendations("path-1", "user-1")

        review_recs = [r for r in result if r["type"] == "review"]
        assert len(review_recs) == 1
        assert "Weak Topic" in review_recs[0]["title"]
        assert "40" in review_recs[0]["reason"]

    @pytest.mark.asyncio
    async def test_review_recommendation_failed(self):
        db = AsyncMock()
        svc = RecommendationService(db)

        mock_path = MagicMock()
        mock_path.active_version_id = "ver-1"

        path_result = MagicMock()
        path_result.scalar_one_or_none.return_value = mock_path

        nodes = [
            _make_node(id="n1", status="failed", mastery=30.0, node_order=1, title="Failed Topic"),
        ]

        nodes_result = MagicMock()
        nodes_result.scalars.return_value.all.return_value = nodes

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return path_result
            elif call_count == 2:
                return nodes_result
            return MagicMock()

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await svc.get_recommendations("path-1", "user-1")

        review_recs = [r for r in result if r["type"] == "review"]
        assert len(review_recs) == 1
        assert "评估未通过" in review_recs[0]["reason"]

    @pytest.mark.asyncio
    async def test_no_recommendations_for_empty_path(self):
        db = AsyncMock()
        svc = RecommendationService(db)

        mock_path = MagicMock()
        mock_path.active_version_id = "ver-1"

        path_result = MagicMock()
        path_result.scalar_one_or_none.return_value = mock_path

        nodes_result = MagicMock()
        nodes_result.scalars.return_value.all.return_value = []

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return path_result
            elif call_count == 2:
                return nodes_result
            return MagicMock()

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await svc.get_recommendations("path-1", "user-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_max_recommendations_limit(self):
        db = AsyncMock()
        svc = RecommendationService(db)

        mock_path = MagicMock()
        mock_path.active_version_id = "ver-1"

        path_result = MagicMock()
        path_result.scalar_one_or_none.return_value = mock_path

        # Create many available nodes — should generate many practice recs
        nodes = [
            _make_node(id=f"n{i}", status="available", mastery=0.0, node_order=i, title=f"Node {i}") for i in range(20)
        ]

        nodes_result = MagicMock()
        nodes_result.scalars.return_value.all.return_value = nodes

        call_count = 0

        async def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return path_result
            elif call_count == 2:
                return nodes_result
            return MagicMock()

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await svc.get_recommendations("path-1", "user-1")
        assert len(result) <= 10  # MAX_RECOMMENDATIONS
