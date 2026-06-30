"""Conftest for integration tests with PostgreSQL DB session support."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import clear_settings_cache, get_settings


@pytest.fixture(autouse=True)
def mock_redis_for_integration():
    """Mock Redis client for integration tests to execute cleanly without network latency."""
    mock_redis = AsyncMock()
    mock_redis.incr.return_value = 1
    with (
        patch("app.core.rate_limit.get_redis", return_value=mock_redis),
        patch("app.core.redis.get_redis", return_value=mock_redis),
    ):
        yield mock_redis


@pytest.fixture
async def db_session():
    """Yield an AsyncSession for integration tests."""
    clear_settings_cache()
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        yield session
