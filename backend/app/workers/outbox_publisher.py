"""Outbox event publisher for reliable message delivery.

Reads pending events from the outbox_events table using SELECT FOR UPDATE
SKIP LOCKED, dispatches them via the shared OutboxDispatcher, and marks
them as published.
"""

from __future__ import annotations

import json
from datetime import timedelta

import structlog
from sqlalchemy import select

from app.common.datetime import utc_now
from app.core.database import get_session_factory
from app.models.outbox import OutboxEvent
from app.workers.outbox_dispatcher import OutboxDispatchError, dispatch_event

logger = structlog.get_logger()

# Exponential backoff base (seconds)
BACKOFF_BASE = 5
MAX_BACKOFF = 300


async def publish_pending_outbox() -> int:
    """Publish pending outbox events to Celery/Redis.

    Uses SELECT FOR UPDATE SKIP LOCKED to prevent duplicate delivery
    across multiple publisher instances.

    Returns the number of events published.
    """
    factory = get_session_factory()
    published = 0

    async with factory() as db:
        now = utc_now()

        # Fetch pending events that are ready for delivery
        result = await db.execute(
            select(OutboxEvent)
            .where(
                OutboxEvent.status == "pending",
                OutboxEvent.attempt_count < OutboxEvent.max_attempts,
                (OutboxEvent.available_at.is_(None)) | (OutboxEvent.available_at <= now),
            )
            .order_by(OutboxEvent.created_at)
            .limit(20)
            .with_for_update(skip_locked=True)
        )
        events = list(result.scalars().all())

        for event in events:
            try:
                payload = event.payload if isinstance(event.payload, dict) else json.loads(event.payload)
                task_id = payload.get("task_id")

                # Define the task execution callback (Celery dispatch)
                async def _celery_dispatch(tid: str) -> None:
                    from app.workers.tasks import execute_background_task

                    execute_background_task.delay(tid)

                execute_task = _celery_dispatch if event.event_type == "task.execute" and task_id else None

                success = await dispatch_event(event, payload, now, execute_task=execute_task)
                if success:
                    published += 1

            except OutboxDispatchError:
                # Permanent failure — mark as failed
                event.status = "failed"
                logger.error("outbox_permanent_failure", event_id=event.id, error=event.last_error)
            except Exception as e:
                # Transient failure — increment attempt count and schedule retry
                event.attempt_count += 1
                event.last_error = str(e)[:1000]

                if event.attempt_count >= event.max_attempts:
                    event.status = "failed"
                    logger.error("outbox_permanent_failure", event_id=event.id, error=str(e))
                else:
                    backoff = min(BACKOFF_BASE * (2**event.attempt_count), MAX_BACKOFF)
                    event.available_at = now + timedelta(seconds=backoff)
                    logger.warning(
                        "outbox_retry_scheduled",
                        event_id=event.id,
                        attempt=event.attempt_count,
                        backoff_seconds=backoff,
                        error=str(e),
                    )

        await db.commit()

    return published


if __name__ == "__main__":
    import asyncio

    async def _main() -> None:
        logger.info("outbox_publisher_started")
        while True:
            try:
                n = await publish_pending_outbox()
                if n > 0:
                    logger.info("outbox_published_events", count=n)
            except Exception as e:
                logger.error("outbox_publisher_loop_error", error=str(e), exc_info=True)
            await asyncio.sleep(2)

    asyncio.run(_main())
