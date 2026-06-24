"""Outbox event publisher for reliable message delivery."""

from __future__ import annotations

import json

import structlog
from sqlalchemy import select

from app.core.database import get_session_factory
from app.core.redis import get_redis
from app.models.task import BackgroundTask, TaskEvent

logger = structlog.get_logger()


async def publish_pending_outbox() -> int:
    """Publish pending outbox events to Redis Pub/Sub.

    Returns the number of events published.
    """
    factory = get_session_factory()
    published = 0

    async with factory() as db:
        # Use SELECT FOR UPDATE SKIP LOCKED to avoid contention
        result = await db.execute(
            select(BackgroundTask)
            .where(BackgroundTask.status == "pending")
            .order_by(BackgroundTask.created_at)
            .limit(10)
            .with_for_update(skip_locked=True)
        )
        tasks = list(result.scalars().all())

        for task in tasks:
            try:
                # Get the latest event for this task
                event_result = await db.execute(
                    select(TaskEvent)
                    .where(TaskEvent.task_id == task.id)
                    .order_by(TaskEvent.sequence_number.desc())
                    .limit(1)
                )
                event = event_result.scalar_one_or_none()

                if event:
                    # Publish to Redis channel
                    redis = get_redis()
                    channel = f"task:{task.id}"
                    await redis.publish(
                        channel,
                        json.dumps(
                            {
                                "event_id": f"{task.id}:{event.sequence_number}",
                                "task_id": task.id,
                                "type": event.event_type,
                                "status": event.status,
                                "progress": event.progress,
                                "stage": event.stage,
                                "message": event.message,
                                "result": event.result,
                                "timestamp": event.created_at.isoformat(),
                            }
                        ),
                    )
                    published += 1
                    logger.info("outbox_published", task_id=task.id, event_type=event.event_type)

            except Exception as e:
                logger.error("outbox_publish_failed", task_id=task.id, error=str(e))

        await db.commit()

    return published
