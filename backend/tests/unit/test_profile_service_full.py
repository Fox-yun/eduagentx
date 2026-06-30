"""Comprehensive unit tests for ProfileService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _mock_scalar_result(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _make_profile(**overrides):
    p = MagicMock()
    p.user_id = overrides.get("user_id", "user-1")
    p.learning_dimensions = overrides.get("learning_dimensions")
    return p


class TestProfileServiceUpdateAfterAssessment:
    @pytest.mark.asyncio
    async def test_llm_update_success(self):
        from app.services.profile import ProfileService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = ProfileService(db)
        profile = _make_profile(
            learning_dimensions={
                "knowledge_depth": 50,
                "practice_ability": 50,
                "learning_efficiency": 50,
                "concept_grasp": 50,
                "problem_solving": 50,
            }
        )
        db.execute = AsyncMock(return_value=_mock_scalar_result(profile))

        llm_result = {
            "dimensions": {
                "knowledge_depth": 60,
                "practice_ability": 55,
                "learning_efficiency": 50,
                "concept_grasp": 55,
                "problem_solving": 45,
            },
            "analysis": "Good progress",
            "suggestion": "Keep practicing",
        }

        with patch("app.services.profile.llm_json", new_callable=AsyncMock, return_value=llm_result):
            result = await svc.update_after_assessment(
                user_id="user-1",
                node_title="Python Basics",
                score=85.0,
                passed=True,
                weak_concepts=["loops"],
            )
            assert result is not None
            assert result["dimensions"]["knowledge_depth"] == 60
            assert result["analysis"] == "Good progress"
            db.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_llm_update_clamp_values(self):
        from app.services.profile import ProfileService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = ProfileService(db)
        profile = _make_profile(
            learning_dimensions={
                "knowledge_depth": 50,
                "practice_ability": 50,
                "learning_efficiency": 50,
                "concept_grasp": 50,
                "problem_solving": 50,
            }
        )
        db.execute = AsyncMock(return_value=_mock_scalar_result(profile))

        llm_result = {
            "dimensions": {
                "knowledge_depth": 150,  # over 100, should clamp
                "practice_ability": -10,  # under 0, should clamp
                "learning_efficiency": 50,
                "concept_grasp": 50,
                "problem_solving": 50,
            },
            "analysis": "",
            "suggestion": "",
        }

        with patch("app.services.profile.llm_json", new_callable=AsyncMock, return_value=llm_result):
            result = await svc.update_after_assessment("user-1", "Node", 80.0, True, [])
            assert result["dimensions"]["knowledge_depth"] == 100
            assert result["dimensions"]["practice_ability"] == 0

    @pytest.mark.asyncio
    async def test_llm_fallback_rule_based_pass(self):
        from app.services.profile import ProfileService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = ProfileService(db)
        profile = _make_profile(
            learning_dimensions={
                "knowledge_depth": 50,
                "practice_ability": 50,
                "learning_efficiency": 50,
                "concept_grasp": 50,
                "problem_solving": 50,
            }
        )
        db.execute = AsyncMock(return_value=_mock_scalar_result(profile))

        with patch("app.services.profile.llm_json", new_callable=AsyncMock, side_effect=Exception("LLM down")):
            result = await svc.update_after_assessment("user-1", "Node", 85.0, True, [])
            assert result is None
            # Rule-based: pass with score >= 80 => +3
            assert profile.learning_dimensions["knowledge_depth"] == 53
            assert profile.learning_dimensions["practice_ability"] == 53

    @pytest.mark.asyncio
    async def test_llm_fallback_rule_based_fail(self):
        from app.services.profile import ProfileService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = ProfileService(db)
        profile = _make_profile(
            learning_dimensions={
                "knowledge_depth": 50,
                "practice_ability": 50,
                "learning_efficiency": 50,
                "concept_grasp": 50,
                "problem_solving": 50,
            }
        )
        db.execute = AsyncMock(return_value=_mock_scalar_result(profile))

        with patch("app.services.profile.llm_json", new_callable=AsyncMock, side_effect=Exception("LLM down")):
            result = await svc.update_after_assessment("user-1", "Node", 40.0, False, ["concept1"])
            assert result is None
            # Rule-based: fail => -2
            assert profile.learning_dimensions["knowledge_depth"] == 48

    @pytest.mark.asyncio
    async def test_profile_not_found(self):
        from app.services.profile import ProfileService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = ProfileService(db)
        db.execute = AsyncMock(return_value=_mock_scalar_result(None))

        result = await svc.update_after_assessment("user-1", "Node", 80.0, True, [])
        assert result is None

    @pytest.mark.asyncio
    async def test_llm_missing_dimensions_use_defaults(self):
        from app.services.profile import ProfileService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = ProfileService(db)
        profile = _make_profile(learning_dimensions=None)  # no existing dimensions
        db.execute = AsyncMock(return_value=_mock_scalar_result(profile))

        llm_result = {
            "dimensions": {
                "knowledge_depth": 70,
                # missing other dimensions
            },
            "analysis": "test",
            "suggestion": "test",
        }

        with patch("app.services.profile.llm_json", new_callable=AsyncMock, return_value=llm_result):
            result = await svc.update_after_assessment("user-1", "Node", 80.0, True, [])
            assert result["dimensions"]["practice_ability"] == 50  # default
            assert result["dimensions"]["knowledge_depth"] == 70

    @pytest.mark.asyncio
    async def test_llm_partial_dimensions_from_current(self):
        from app.services.profile import ProfileService

        db = AsyncMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        db.add = MagicMock()
        db.add_all = MagicMock()
        svc = ProfileService(db)
        profile = _make_profile(
            learning_dimensions={
                "knowledge_depth": 60,
                "practice_ability": 40,
                "learning_efficiency": 55,
                "concept_grasp": 45,
                "problem_solving": 50,
            }
        )
        db.execute = AsyncMock(return_value=_mock_scalar_result(profile))

        llm_result = {
            "dimensions": {
                "knowledge_depth": 65,
                # other dimensions missing from LLM but present in current
            },
            "analysis": "",
            "suggestion": "",
        }

        with patch("app.services.profile.llm_json", new_callable=AsyncMock, return_value=llm_result):
            result = await svc.update_after_assessment("user-1", "Node", 80.0, True, [])
            assert result["dimensions"]["practice_ability"] == 40  # from current
            assert result["dimensions"]["knowledge_depth"] == 65
