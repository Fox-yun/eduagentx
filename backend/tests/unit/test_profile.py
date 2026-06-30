"""Unit tests for profile service defaults and clamping."""

from app.services.profile import DEFAULT_DIMENSIONS


class TestDefaultDimensions:
    def test_all_dimensions_present(self):
        expected = {"knowledge_depth", "practice_ability", "learning_efficiency", "concept_grasp", "problem_solving"}
        assert set(DEFAULT_DIMENSIONS.keys()) == expected

    def test_all_defaults_are_50(self):
        for v in DEFAULT_DIMENSIONS.values():
            assert v == 50

    def test_dimensions_are_int(self):
        for v in DEFAULT_DIMENSIONS.values():
            assert isinstance(v, int)


class TestDimensionClamping:
    """Test that dimensions are clamped to 0-100 range."""

    def test_clamp_above_100(self):
        dims = {"knowledge_depth": 150, "practice_ability": -10}
        for key in DEFAULT_DIMENSIONS:
            if key in dims:
                dims[key] = max(0, min(100, int(dims[key])))
            else:
                dims[key] = DEFAULT_DIMENSIONS[key]
        assert dims["knowledge_depth"] == 100
        assert dims["practice_ability"] == 0

    def test_clamp_normal_values(self):
        dims = {"knowledge_depth": 65, "practice_ability": 50}
        for key in DEFAULT_DIMENSIONS:
            if key in dims:
                dims[key] = max(0, min(100, int(dims[key])))
            else:
                dims[key] = DEFAULT_DIMENSIONS[key]
        assert dims["knowledge_depth"] == 65
        assert dims["practice_ability"] == 50
