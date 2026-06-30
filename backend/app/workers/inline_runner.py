"""Inline task runner for local development.

Polls the outbox for pending events and dispatches them via the shared
OutboxDispatcher. Background tasks are executed directly in the FastAPI
process, bypassing Celery and Redis.
Only used when app_env == 'development'.
"""

from __future__ import annotations

import asyncio
import json

import structlog

from app.core.database import get_session_factory
from app.models.outbox import OutboxEvent
from app.workers.outbox_dispatcher import OutboxDispatchError, dispatch_event
from app.workers.task_handlers import get_handler
from app.workers.task_runtime import update_task_status

logger = structlog.get_logger()

POLL_INTERVAL_SECONDS = 2


async def _execute_task_inline(task_id: str) -> None:
    """Execute a background task inline (same process, no Celery)."""
    factory = get_session_factory()
    async with factory() as db:
        from sqlalchemy import select

        from app.models.task import BackgroundTask

        result = await db.execute(select(BackgroundTask).where(BackgroundTask.id == task_id))
        task = result.scalar_one_or_none()

        if not task:
            logger.error("inline_task_not_found", task_id=task_id)
            return

        await update_task_status(db, task_id, "running", progress=0, stage="starting", message="Task started")

        try:
            handler = get_handler(task.task_type)
            if handler is None:
                await update_task_status(
                    db,
                    task_id,
                    "failed",
                    error_code="UNKNOWN_TASK_TYPE",
                    error_message=f"Unknown task type: {task.task_type}",
                )
                return

            task_result = await handler(db, task)

            await update_task_status(
                db,
                task_id,
                "completed",
                progress=100,
                stage="completed",
                message="Task completed",
                result=task_result,
            )
            logger.info("inline_task_completed", task_id=task_id, task_type=task.task_type)

        except Exception as e:
            logger.error("inline_task_failed", task_id=task_id, error=str(e))
            await update_task_status(
                db,
                task_id,
                "failed",
                error_code="EXECUTION_ERROR",
                error_message=str(e),
            )


async def _process_outbox_once() -> int:
    """Poll outbox and dispatch events inline. Returns count of dispatched events."""
    from app.common.datetime import utc_now

    factory = get_session_factory()
    dispatched = 0

    async with factory() as db:
        from sqlalchemy import select

        now = utc_now()
        result = await db.execute(
            select(OutboxEvent)
            .where(
                OutboxEvent.status == "pending",
                OutboxEvent.attempt_count < OutboxEvent.max_attempts,
                (OutboxEvent.available_at.is_(None)) | (OutboxEvent.available_at <= now),
            )
            .order_by(OutboxEvent.created_at)
            .limit(10)
            .with_for_update(skip_locked=True)
        )
        events = list(result.scalars().all())

        # Diagnostic: log poll results
        if not events:
            from sqlalchemy import func

            pending_count = await db.execute(
                select(func.count()).select_from(OutboxEvent).where(OutboxEvent.status == "pending")
            )
            count = pending_count.scalar() or 0
            if count > 0:
                logger.warning("outbox_pending_not_picked", pending_count=count, now=str(now))

        for event in events:
            try:
                payload = event.payload if isinstance(event.payload, dict) else json.loads(event.payload)
                task_id = payload.get("task_id")

                # For task.execute events, use inline execution
                async def _inline_execute(tid: str) -> None:
                    asyncio.create_task(_execute_task_inline(tid))

                execute_task = _inline_execute if event.event_type == "task.execute" and task_id else None

                success = await dispatch_event(event, payload, now, execute_task=execute_task)
                if success:
                    dispatched += 1

            except OutboxDispatchError:
                event.status = "failed"
                logger.error("inline_outbox_permanent_failure", event_id=event.id, error=event.last_error)
            except Exception as e:
                event.attempt_count += 1
                event.last_error = str(e)[:1000]
                logger.warning("inline_outbox_error", event_id=event.id, error=str(e))

        await db.commit()

    return dispatched


async def run_inline_outbox_poller(stop_event: asyncio.Event) -> None:
    """Background poller loop. Runs until stop_event is set."""
    logger.info("inline_outbox_poller_started", interval=POLL_INTERVAL_SECONDS)
    while not stop_event.is_set():
        try:
            count = await _process_outbox_once()
            if count > 0:
                logger.info("inline_outbox_dispatched", count=count)
        except Exception as e:
            logger.warning("inline_outbox_poll_error", error=str(e))
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=POLL_INTERVAL_SECONDS)
            break  # stop_event was set
        except TimeoutError:
            pass  # normal timeout, continue polling
    logger.info("inline_outbox_poller_stopped")
