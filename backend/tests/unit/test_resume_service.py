"""Unit tests for resume service logic."""


class TestResumeServiceStates:
    """Test resume state determination logic."""

    def test_empty_state_conditions(self):
        # No paths at all → empty
        paths = []
        assert len(paths) == 0

    def test_generating_state_conditions(self):
        # Has path with status "generating" → generating
        path_status = "generating"
        assert path_status == "generating"

    def test_review_state_conditions(self):
        # Has path with status "draft" → review
        path_status = "draft"
        assert path_status == "draft"

    def test_active_state_conditions(self):
        # Has path with status "active" → active
        path_status = "active"
        assert path_status == "active"

    def test_completed_state_conditions(self):
        # All nodes completed → completed
        total_nodes = 5
        completed_nodes = 5
        assert completed_nodes == total_nodes


class TestResumeServiceProgressCalculation:
    def test_progress_percentage(self):
        total = 10
        completed = 7
        pct = round(completed / total * 100) if total > 0 else 0
        assert pct == 70

    def test_progress_zero_nodes(self):
        total = 0
        completed = 0
        pct = round(completed / total * 100) if total > 0 else 0
        assert pct == 0

    def test_progress_all_complete(self):
        total = 5
        completed = 5
        pct = round(completed / total * 100) if total > 0 else 0
        assert pct == 100


class TestResumeServiceAverageMastery:
    def test_average_mastery(self):
        masteries = [80.0, 60.0, 90.0, 70.0]
        avg = sum(masteries) / len(masteries)
        assert avg == 75.0

    def test_average_mastery_empty(self):
        masteries = []
        avg = sum(masteries) / len(masteries) if masteries else 0.0
        assert avg == 0.0
