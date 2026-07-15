"""Task runtime utilities for worker tasks.

Single source of truth for task state transitions and event creation.
Both routers and workers must use ``update_task_status`` / ``transition_task``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import TERMINAL_TASK_STATUSES, TaskEventType, TaskStatus
from app.models.task import BackgroundTask, TaskEvent


def record_agent_step(
    task: BackgroundTask,
    *,
    agent_key: str,
    label: str,
    status: str,
    summary: str,
    iteration: int = 1,
    artifact_type: str | None = None,
) -> None:
    """Append or update one durable, user-visible agent collaboration step.

    The task is already attached to the worker session. Copy-then-assign keeps
    SQLAlchemy JSON change tracking reliable; the next task status update
    commits the trace together with its SSE progress event.
    """
    now = datetime.now(UTC).isoformat()
    existing_trace = task.agent_trace if isinstance(task.agent_trace, list) else []
    trace = [dict(item) for item in existing_trace if isinstance(item, dict)]
    step = next(
        (
            item
            for item in trace
            if item.get("agent_key") == agent_key and item.get("iteration", 1) == iteration
        ),
        None,
    )
    if step is None:
        step = {
            "agent_key": agent_key,
            "label": label,
            "iteration": iteration,
            "status": status,
            "summary": summary,
            "artifact_type": artifact_type,
            "started_at": now,
            "completed_at": None,
        }
        trace.append(step)
    else:
        step.update(
            {
                "label": label,
                "status": status,
                "summary": summary,
                "artifact_type": artifact_type or step.get("artifact_type"),
            }
        )

    if status in {"completed", "failed", "needs_revision"}:
        step["completed_at"] = now
    task.agent_trace = trace


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
    """Update task status and create event atomically using UPDATE … RETURNING.

    The sequence number is incremented in the database with
    ``UPDATE … RETURNING``, eliminating race conditions between concurrent
    writers.  The task update and event insertion happen in the same
    transaction.
    """
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

    # Atomic sequence number increment with RETURNING
    seq_result = await db.execute(
        update(BackgroundTask)
        .where(BackgroundTask.id == task_id)
        .values(next_event_sequence=BackgroundTask.next_event_sequence + 1)
        .returning(BackgroundTask.next_event_sequence)
    )
    next_sequence = seq_result.scalar_one()
    sequence = next_sequence - 1  # The sequence for this event

    event_type = _status_to_event_type(target_status)
    event = TaskEvent(
        id=str(uuid.uuid4()),
        task_id=task_id,
        sequence_number=sequence,
        event_type=event_type,
        status=target_status,
        progress=task.progress,
        stage=task.current_stage,
        message=task.message,
        result=task.result,
    )
    db.add(event)

    # Commit immediately so SSE stream can see the event in real-time
    await db.commit()
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


async def recover_stale_tasks(
    db: AsyncSession,
    *,
    finalize_cancel_requests: bool = False,
) -> list[str]:
    """Find and recover stale tasks.

    Tasks that are in 'running' state but haven't updated their heartbeat
    are marked as 'interrupted' so they can be retried.
    """
    from datetime import timedelta

    stale_threshold = datetime.now(UTC) - timedelta(minutes=5)

    cancel_condition = BackgroundTask.status == TaskStatus.CANCEL_REQUESTED.value
    if not finalize_cancel_requests:
        cancel_condition = and_(cancel_condition, BackgroundTask.heartbeat_at < stale_threshold)

    result = await db.execute(
        select(BackgroundTask).where(
            or_(
                and_(
                    BackgroundTask.status == TaskStatus.RUNNING.value,
                    BackgroundTask.heartbeat_at < stale_threshold,
                ),
                cancel_condition,
            )
        )
    )
    stale_tasks = list(result.scalars().all())

    recovered_ids = []
    for task in stale_tasks:
        if task.status == TaskStatus.CANCEL_REQUESTED.value:
            task.status = TaskStatus.CANCELLED.value
            task.message = "Task cancelled after worker interruption"
            task.completed_at = datetime.now(UTC)
            task.next_event_sequence += 1
            db.add(
                TaskEvent(
                    id=str(uuid.uuid4()),
                    task_id=task.id,
                    sequence_number=task.next_event_sequence - 1,
                    event_type=TaskEventType.CANCELLED.value,
                    status=TaskStatus.CANCELLED.value,
                    progress=task.progress,
                    stage=task.current_stage,
                    message=task.message,
                    result=task.result,
                )
            )
            await _cleanup_cancelled_task_target(db, task)
            recovered_ids.append(task.id)
            continue

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
    await db.commit()
    return recovered_ids


async def _cleanup_cancelled_task_target(db: AsyncSession, task: BackgroundTask) -> None:
    """Release domain rows owned by a cancelled task whose worker disappeared."""
    if task.task_type != "learning_unit_generation":
        return

    from app.models.unit import LearningUnitContent, LearningUnitContentVersion

    metadata = task.target_metadata or {}
    version_id = metadata.get("unit_content_version_id")
    if version_id:
        version_result = await db.execute(
            select(LearningUnitContentVersion).where(LearningUnitContentVersion.id == version_id)
        )
        version = version_result.scalar_one_or_none()
        if version and version.status == "generating":
            version.status = "failed"
            version.error_code = "TASK_CANCELLED"
            version.error_message = "Generation worker was interrupted and the task was cancelled"
            version.completed_at = datetime.now(UTC)

    content_result = await db.execute(
        select(LearningUnitContent).where(LearningUnitContent.active_task_id == task.id)
    )
    content = content_result.scalar_one_or_none()
    if content:
        content.active_task_id = None
        content.status = "ready" if content.active_version_id else "failed"
        content.last_error_code = "TASK_CANCELLED"
        content.last_error_message = "Generation was cancelled after the worker was interrupted"
