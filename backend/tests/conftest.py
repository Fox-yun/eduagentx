"""Root conftest for all tests."""

from __future__ import annotations

import os

# Set test environment before any imports
os.environ["APP_ENV"] = "test"
os.environ["APP_SECRET_KEY"] = "test-secret-key-at-least-32-chars-long"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://eduagentx:eduagentx@localhost:5432/eduagentx_test"
os.environ["REDIS_URL"] = "redis://localhost:6379/1"
os.environ["COOKIE_SECURE"] = "false"

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    """Create an async test client with mocked database and Redis."""
    with (
        patch("app.main.check_database_connection", new_callable=AsyncMock, return_value=True),
        patch("app.core.redis.check_redis_connection", new_callable=AsyncMock, return_value=True),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
