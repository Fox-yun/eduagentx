"""Redis connection pool and utilities."""

from __future__ import annotations

import redis.asyncio as redis

from app.config import get_settings

_redis_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    """Get or create the Redis client."""
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=20,
        )
    return _redis_client


async def check_redis_connection() -> bool:
    """Check if Redis is reachable."""
    try:
        client = get_redis()
        await client.ping()
        return True
    except Exception:
        return False


async def close_redis() -> None:
    """Close the Redis connection."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None
