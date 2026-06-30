"""Background task service."""

from __future__ import annotations

import uuid
from datetime import timedelta

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.datetime import utc_now
from app.common.enums import TERMINAL_TASK_STATUSES, TaskEventType, TaskStatus
from app.core.errors import ApiError
from app.core.pagination import decode_cursor, encode_cursor
from app.models.task import BackgroundTask, TaskEvent, validate_task_transition

logger = structlog.get_logger()


class TaskService:
    """Background task business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_task(
        self,
        user_id: str,
        task_type: str,
        target_type: str | None = None,
        target_id: str | None = None,
        target_metadata: dict | None = None,
        request_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> BackgroundTask:
        """Create a new background task."""
        # Check idempotency
        if idempotency_key:
            existing = await self.db.execute(
                select(BackgroundTask).where(BackgroundTask.idempotency_key == idempotency_key)
            )
            existing_task = existing.scalar_one_or_none()
            if existing_task:
                return existing_task

        task = BackgroundTask(
            id=str(uuid.uuid4()),
            user_id=user_id,
            task_type=task_type,
            status=TaskStatus.PENDING.value,
            target_type=target_type,
            target_id=target_id,
            target_metadata=target_metadata,
            request_id=request_id,
            idempotency_key=idempotency_key,
            expires_at=utc_now() + timedelta(hours=24),
        )
        self.db.add(task)

        # Create initial event
        await self._add_event(task.id, 0, TaskEventType.SNAPSHOT.value, TaskStatus.PENDING.value, 0, "任务已创建")

        # Publish to outbox for worker pickup
        await self._publish_to_outbox(task)

        await self.db.flush()
        await self.db.commit()
        return task

    async def get_task(self, task_id: str, user_id: str) -> BackgroundTask:
        """Get a task by ID, ensuring ownership."""
        result = await self.db.execute(
            select(BackgroundTask).where(
                BackgroundTask.id == task_id,
                BackgroundTask.user_id == user_id,
            )
        )
        task = result.scalar_one_or_none()
        if not task:
            raise ApiError(code="TASK_NOT_FOUND", message="Task not found", status_code=404)
        return task

    async def list_tasks(
        self,
        user_id: str,
        cursor: str | None = None,
        limit: int = 20,
    ) -> dict:
        """List tasks for a user with cursor pagination."""
        if limit < 1 or limit > 100:
            limit = 20

        query = select(BackgroundTask).where(BackgroundTask.user_id == user_id)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply cursor
        if cursor:
            cursor_data = decode_cursor(cursor)
            cursor_created = cursor_data.get("order")
            cursor_id = cursor_data.get("id")
            if cursor_created and cursor_id:
                query = query.where(
                    (BackgroundTask.created_at < cursor_created)
                    | ((BackgroundTask.created_at == cursor_created) & (BackgroundTask.id < cursor_id))
                )

        query = query.order_by(BackgroundTask.created_at.desc(), BackgroundTask.id.desc())
        query = query.limit(limit + 1)

        result = await self.db.execute(query)
        tasks = list(result.scalars().all())

        has_next = len(tasks) > limit
        if has_next:
            tasks = tasks[:limit]
            last = tasks[-1]
            next_cursor = encode_cursor(
                {
                    "order": str(last.created_at),
                    "id": last.id,
                }
            )
        else:
            next_cursor = None

        return {
            "items": tasks,
            "next_cursor": next_cursor,
            "total": total,
        }

    async def update_task_status(
        self,
        task_id: str,
        target_status: str,
        progress: int | None = None,
        stage: str | None = None,
        message: str | None = None,
        result: dict | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> BackgroundTask:
        """Update task status with validation."""
        result_query = await self.db.execute(select(BackgroundTask).where(BackgroundTask.id == task_id))
        task = result_query.scalar_one_or_none()
        if not task:
            raise ApiError(code="TASK_NOT_FOUND", message="Task not found", status_code=404)

        if not validate_task_transition(task.status, target_status):
            raise ApiError(
                code="INVALID_TRANSITION",
                message=f"Cannot transition from '{task.status}' to '{target_status}'",
                status_code=400,
            )

        from app.workers.task_runtime import update_task_status as _transition_task

        return await _transition_task(
            self.db,
            task_id,
            target_status,
            progress=progress,
            stage=stage,
            message=message,
            result=result,
            error_code=error_code,
            error_message=error_message,
        )

    async def cancel_task(self, task_id: str, user_id: str) -> BackgroundTask:
        """Request task cancellation."""
        task = await self.get_task(task_id, user_id)

        if task.status in TERMINAL_TASK_STATUSES:
            raise ApiError(
                code="TASK_ALREADY_COMPLETED", message="Task is already in a terminal state", status_code=400
            )

        if task.status == TaskStatus.PENDING.value:
            return await self.update_task_status(task_id, TaskStatus.CANCELLED.value, message="任务已取消")
        else:
            return await self.update_task_status(task_id, TaskStatus.CANCEL_REQUESTED.value, message="正在取消...")

    async def get_task_events(
        self,
        task_id: str,
        after_sequence: int | None = None,
    ) -> list[TaskEvent]:
        """Get task events, optionally after a specific sequence number."""
        query = select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.sequence_number)
        if after_sequence is not None:
            query = query.where(TaskEvent.sequence_number > after_sequence)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def _add_event(
        self,
        task_id: str,
        sequence_number: int,
        event_type: str,
        status: str,
        progress: int = 0,
        message: str | None = None,
        result: dict | None = None,
        stage: str | None = None,
    ) -> TaskEvent:
        """Add a task event."""
        event = TaskEvent(
            id=str(uuid.uuid4()),
            task_id=task_id,
            sequence_number=sequence_number,
            event_type=event_type,
            status=status,
            progress=progress,
            stage=stage,
            message=message,
            result=result,
        )
        self.db.add(event)
        return event

    async def _publish_to_outbox(self, task: BackgroundTask) -> None:
        """Write outbox event for reliable delivery via outbox publisher.

        The event is written in the same transaction as the task creation,
        ensuring no task is lost even if the broker is temporarily unavailable.
        """
        import json

        from app.models.outbox import OutboxEvent

        outbox = OutboxEvent(
            id=str(uuid.uuid4()),
            event_type="task.execute",
            aggregate_type="BackgroundTask",
            aggregate_id=task.id,
            payload=json.dumps({"task_id": task.id, "task_type": task.task_type}),
            status="pending",
        )
        self.db.add(outbox)
        logger.info("outbox_event_created", task_id=task.id, task_type=task.task_type)

    def _status_to_event_type(self, status: str) -> str:
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
