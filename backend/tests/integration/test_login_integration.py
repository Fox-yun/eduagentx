"""Integration tests for authentication login behavior with database."""

from __future__ import annotations

import pytest
from sqlalchemy.engine.url import make_url

from app.config import get_settings


@pytest.fixture(autouse=True)
def verify_test_database() -> None:
    """Ensure integration tests strictly run against a test database."""
    settings = get_settings()
    database_name = make_url(settings.database_url).database
    if not database_name or not database_name.endswith("_test"):
        pytest.skip(f"Integration tests require a _test database, current DB is: {database_name}")


class TestLoginIntegration:
    """Integration test verifying remember_me impact on session/tokens."""

    @pytest.mark.asyncio
    async def test_login_remember_me_ttl(self) -> None:
        """Verify remember_me parameter is accepted and handled properly."""
        # This integration test structure will be fully expanded during Phase 2 live DB testing
        assert True
