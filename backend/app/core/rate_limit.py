"""Redis-backed rate limiting utility."""

from __future__ import annotations

import hashlib

import structlog

from app.config import get_settings
from app.core.errors import ApiError
from app.core.redis import get_redis

logger = structlog.get_logger()


async def check_rate_limit(key_prefix: str, identifier: str, max_requests: int, window_seconds: int) -> None:
    """Check and increment rate limit counter in Redis using fixed window.

    Raises ApiError(429) if limit exceeded.
    If Redis is unreachable in test/dev/prod, logs warning and allows (or blocks on prod if configured).
    """
    settings = get_settings()
    # Hash identifier (email/IP) to prevent PII in Redis keys
    hashed_id = hashlib.sha256(identifier.strip().lower().encode("utf-8")).hexdigest()
    redis_key = f"ratelimit:{key_prefix}:{hashed_id}"

    try:
        redis = get_redis()
        current = await redis.incr(redis_key)
        if current == 1:
            await redis.expire(redis_key, window_seconds)

        if current > max_requests:
            logger.warning("rate_limit_exceeded", key_prefix=key_prefix, count=current)
            raise ApiError(
                code="TOO_MANY_REQUESTS",
                message="Too many requests. Please try again later.",
                status_code=429,
            )
    except ApiError:
        raise
    except Exception as e:
        logger.warning("rate_limit_redis_error", error=str(e))
        if settings.is_production:
            raise ApiError(
                code="SERVICE_UNAVAILABLE",
                message="Rate limiting service unavailable",
                status_code=503,
            ) from e
