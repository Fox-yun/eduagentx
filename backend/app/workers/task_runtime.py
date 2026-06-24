"""Task runtime utilities for worker tasks."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import TERMINAL_TASK_STATUSES, TaskEventType, TaskStatus
from app.models.task import BackgroundTask, TaskEvent


async def update_task_status(
    db: AsyncSession,
    task_id: str,
    target_status: str,
    progress: int | None = None,
    stage: str | None = None,
    message: str | None = None,
    result: dict[str, object] | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> BackgroundTask:
    """Update task status and create event atomically."""
    result_query = await db.execute(select(BackgroundTask).where(BackgroundTask.id == task_id))
    task = result_query.scalar_one_or_none()

    if not task:
        raise ValueError(f"Task {task_id} not found")

    task.status = target_status
    if progress is not None:
        task.progress = progress
    if stage is not None:
        task.current_stage = stage
    if message is not None:
        task.message = message
    if result is not None:
        task.result = result
    if error_code is not None:
        task.error_code = error_code
    if error_message is not None:
        task.error_message = error_message

    if target_status in TERMINAL_TASK_STATUSES:
        task.completed_at = datetime.now(UTC)
    if target_status == TaskStatus.RUNNING.value:
        task.started_at = datetime.now(UTC)

    # Update heartbeat
    task.heartbeat_at = datetime.now(UTC)

    # Atomic sequence number increment
    await db.execute(
        update(BackgroundTask)
        .where(BackgroundTask.id == task_id)
        .values(next_event_sequence=BackgroundTask.next_event_sequence + 1)
    )
    await db.refresh(task, ["next_event_sequence"])

    event_type = _status_to_event_type(target_status)
    event = TaskEvent(
        id=str(uuid.uuid4()),
        task_id=task_id,
        sequence_number=task.next_event_sequence - 1,
        event_type=event_type,
        status=target_status,
        progress=task.progress,
        stage=task.current_stage,
        message=task.message,
        result=task.result,
    )
    db.add(event)

    await db.flush()
    return task


def _status_to_event_type(status: str) -> str:
    """Map task status to event type."""
    mapping = {
        TaskStatus.PENDING.value: TaskEventType.SNAPSHOT.value,
        TaskStatus.RUNNING.value: TaskEventType.PROGRESS.value,
        TaskStatus.COMPLETED.value: TaskEventType.COMPLETED.value,
        TaskStatus.PARTIAL_COMPLETED.value: TaskEventType.PARTIAL_COMPLETED.value,
        TaskStatus.FAILED.value: TaskEventType.FAILED.value,
        TaskStatus.CANCELLED.value: TaskEventType.CANCELLED.value,
        TaskStatus.CANCEL_REQUESTED.value: TaskEventType.PROGRESS.value,
    }
    return mapping.get(status, TaskEventType.PROGRESS.value)


async def recover_stale_tasks(db: AsyncSession) -> list[str]:
    """Find and recover stale tasks.

    Tasks that are in 'running' state but haven't updated their heartbeat
    are marked as 'interrupted' so they can be retried.
    """
    from datetime import timedelta

    stale_threshold = datetime.now(UTC) - timedelta(minutes=5)

    result = await db.execute(
        select(BackgroundTask).where(
            BackgroundTask.status == TaskStatus.RUNNING.value,
            BackgroundTask.heartbeat_at < stale_threshold,
        )
    )
    stale_tasks = list(result.scalars().all())

    recovered_ids = []
    for task in stale_tasks:
        if task.retry_count < task.max_retries:
            # Can retry
            task.status = TaskStatus.INTERRUPTED.value
            task.retry_count += 1
            recovered_ids.append(task.id)
        else:
            # Max retries exceeded
            task.status = TaskStatus.FAILED.value
            task.error_code = "MAX_RETRIES_EXCEEDED"
            task.error_message = "Task failed after maximum retry attempts"
            task.completed_at = datetime.now(UTC)

    await db.flush()
    return recovered_ids
