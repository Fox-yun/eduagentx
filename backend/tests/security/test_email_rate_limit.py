"""Security tests for Email Rate Limiting & Identifier Hashing."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.errors import ApiError
from app.core.rate_limit import check_rate_limit


@pytest.mark.asyncio
async def test_rate_limit_hashes_identifier() -> None:
    """Ensure raw email / IP is hashed before sending to Redis."""
    mock_redis = AsyncMock()
    mock_redis.incr.return_value = 1

    with patch("app.core.rate_limit.get_redis", return_value=mock_redis):
        await check_rate_limit("test_limit", "raw_user@example.com", max_requests=5, window_seconds=60)

    mock_redis.incr.assert_called_once()
    key = mock_redis.incr.call_args[0][0]
    assert "raw_user@example.com" not in key
    assert key.startswith("ratelimit:test_limit:")


@pytest.mark.asyncio
async def test_rate_limit_exceeded_raises_429() -> None:
    """Ensure exceeding rate limit raises 429 ApiError."""
    mock_redis = AsyncMock()
    mock_redis.incr.return_value = 6

    with patch("app.core.rate_limit.get_redis", return_value=mock_redis):
        with pytest.raises(ApiError) as exc_info:
            await check_rate_limit("test_limit", "user@example.com", max_requests=5, window_seconds=60)

    assert exc_info.value.status_code == 429
    assert exc_info.value.code == "TOO_MANY_REQUESTS"
