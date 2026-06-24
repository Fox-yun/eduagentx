"""FastAPI lifespan context manager for startup and shutdown."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import structlog

from app.config import get_settings
from app.core.database import close_database, get_engine
from app.core.logging import setup_logging
from app.core.redis import close_redis, get_redis

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: object) -> AsyncGenerator[None, None]:
    """FastAPI lifespan context manager."""
    setup_logging()
    settings = get_settings()
    logger.info("starting_up", env=settings.app_env)

    # Initialize database engine
    get_engine()
    logger.info("database_initialized")

    # Initialize Redis
    get_redis()
    logger.info("redis_initialized")

    yield

    # Shutdown
    logger.info("shutting_down")
    await close_database()
    await close_redis()
    logger.info("shutdown_complete")
