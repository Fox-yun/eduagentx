"""FastAPI lifespan context manager for startup and shutdown."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
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

    # Initialize database engine (graceful failure)
    try:
        get_engine()
        logger.info("database_initialized")
    except Exception as e:
        logger.warning("database_init_failed", error=str(e))

    # Initialize Redis (graceful failure)
    try:
        get_redis()
        logger.info("redis_initialized")
    except Exception as e:
        logger.warning("redis_init_failed", error=str(e))

    # In development mode, start inline outbox poller (bypasses Celery)
    inline_stop: asyncio.Event | None = None
    inline_task: asyncio.Task | None = None
    if settings.app_env == "development":
        try:
            from app.core.database import get_session_factory
            from app.workers.task_runtime import recover_stale_tasks

            async with get_session_factory()() as recovery_db:
                recovered = await recover_stale_tasks(recovery_db, finalize_cancel_requests=True)
            if recovered:
                logger.info("stale_tasks_recovered_on_startup", task_ids=recovered)

            # Register all task handlers so the inline runner can dispatch them
            from app.workers.task_handlers import register_builtin_task_handlers

            register_builtin_task_handlers()
            logger.info("task_handlers_registered")

            from app.workers.inline_runner import run_inline_outbox_poller

            inline_stop = asyncio.Event()
            inline_task = asyncio.create_task(run_inline_outbox_poller(inline_stop))
            logger.info("inline_task_runner_started")
        except Exception as e:
            logger.warning("inline_task_runner_failed", error=str(e))

    yield

    # Shutdown
    logger.info("shutting_down")
    if inline_stop is not None:
        inline_stop.set()
    if inline_task is not None:
        inline_task.cancel()
        with suppress(asyncio.CancelledError):
            await inline_task
    with suppress(Exception):
        await close_database()
    with suppress(Exception):
        await close_redis()
    logger.info("shutdown_complete")
