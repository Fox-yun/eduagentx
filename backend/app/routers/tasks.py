"""Background task API endpoints with SSE support."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.datetime import to_iso_string
from app.common.enums import TERMINAL_TASK_STATUSES
from app.common.schemas import CursorPage
from app.core.auth_deps import require_learning_user
from app.core.database import get_db
from app.models.task import BackgroundTask
from app.models.user import User
from app.services.task import TaskService

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

router = APIRouter()


def _task_to_dict(task: Any) -> dict[str, Any]:
    """Convert a BackgroundTask to API response dict."""
    return {
        "task_id": task.id,
        "type": task.task_type,
        "title": task.message or task.task_type,
        "status": task.status,
        "progress": task.progress,
        "current_stage": task.current_stage,
        "message": task.message,
        "result": task.result,
        "error": task.error_message,
        "request_id": task.request_id,
        "created_at": to_iso_string(task.created_at),
        "updated_at": to_iso_string(task.updated_at),
    }


def _event_to_sse(event: Any) -> dict[str, Any]:
    """Convert a TaskEvent to SSE data format."""
    return {
        "event_id": f"{event.task_id}:{event.sequence_number}",
        "task_id": event.task_id,
        "type": event.event_type,
        "status": event.status,
        "progress": event.progress,
        "stage": event.stage,
        "message": event.message,
        "result": event.result,
        "timestamp": to_iso_string(event.created_at),
    }


@router.get("", response_model=CursorPage[dict[str, Any]])
async def list_tasks(
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> CursorPage[dict[str, Any]]:
    """List background tasks with cursor pagination."""
    service = TaskService(db)
    result = await service.list_tasks(
        user_id=user.id,
        cursor=cursor,
        limit=limit,
    )

    return CursorPage(
        items=[_task_to_dict(t) for t in result["items"]],
        next_cursor=result["next_cursor"],
        total=result["total"],
    )


@router.get("/{task_id}")
async def get_task(
    task_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get a specific task."""
    service = TaskService(db)
    task = await service.get_task(task_id, user.id)
    return _task_to_dict(task)


@router.post("/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Cancel a running task."""
    service = TaskService(db)
    task = await service.cancel_task(task_id, user.id)
    return _task_to_dict(task)


@router.get("/{task_id}/stream")
async def stream_task_events(
    task_id: str,
    request: Request,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream task events via SSE.

    Supports:
    - Last-Event-ID header for reconnection
    - Real-time updates via polling (Redis Pub/Sub in production)
    - Heartbeat every 15 seconds
    - Auto-close on terminal state

    Note: The initial DB session (from get_db) is used only for ownership
    verification. The event generator creates short-lived sessions for each
    query to avoid holding a connection from the pool for the entire stream.
    """
    from app.core.database import get_session_factory

    service = TaskService(db)

    # Verify ownership (uses the request-scoped session)
    task = await service.get_task(task_id, user.id)
    task_status = task.status
    task_progress = task.progress
    task_stage = task.current_stage
    task_created_at = task.created_at

    # Check for Last-Event-ID
    last_event_id = request.headers.get("last-event-id")
    after_sequence = None
    if last_event_id:
        try:
            # Format: task_id:sequence_number
            parts = last_event_id.split(":")
            if len(parts) == 2:
                after_sequence = int(parts[1])
        except (ValueError, IndexError):
            pass

    # Release the request-scoped session before entering the generator
    await db.close()

    session_factory = get_session_factory()

    async def event_generator() -> AsyncGenerator[str, None]:
        """Generate SSE events using short-lived DB sessions."""
        # Send any missed events first
        async with session_factory() as gen_db:
            gen_service = TaskService(gen_db)
            events = await gen_service.get_task_events(task_id, after_sequence)

        for event in events:
            sse_data = _event_to_sse(event)
            yield f"id: {sse_data['event_id']}\n"
            yield f"event: {sse_data['type']}\n"
            yield f"data: {json.dumps(sse_data)}\n\n"

            # If task is in terminal state, close after sending events
            if event.status in TERMINAL_TASK_STATUSES:
                return

        # Poll for new events
        last_seq = events[-1].sequence_number if events else 0
        heartbeat_count = 0

        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                break

            # Wait a bit before polling
            await asyncio.sleep(1.0)
            heartbeat_count += 1

            # Send heartbeat every 15 seconds
            if heartbeat_count >= 15:
                heartbeat_data = {
                    "event_id": f"{task_id}:heartbeat",
                    "task_id": task_id,
                    "type": "heartbeat",
                    "status": task_status,
                    "progress": task_progress,
                    "stage": task_stage,
                    "message": None,
                    "result": None,
                    "timestamp": to_iso_string(task_created_at),
                }
                yield "event: heartbeat\n"
                yield f"data: {json.dumps(heartbeat_data)}\n\n"
                heartbeat_count = 0

            # Check for new events with a fresh session
            async with session_factory() as gen_db:
                gen_service = TaskService(gen_db)
                new_events = await gen_service.get_task_events(task_id, last_seq)

                if new_events:
                    # Refresh task state
                    task_result = await gen_db.execute(
                        select(BackgroundTask).where(
                            BackgroundTask.id == task_id,
                            BackgroundTask.user_id == user.id,
                        )
                    )
                    updated_task = task_result.scalar_one_or_none()
                    if updated_task:
                        nonlocal task_status, task_progress, task_stage
                        task_status = updated_task.status
                        task_progress = updated_task.progress
                        task_stage = updated_task.current_stage

            if new_events:
                for event in new_events:
                    sse_data = _event_to_sse(event)
                    yield f"id: {sse_data['event_id']}\n"
                    yield f"event: {sse_data['type']}\n"
                    yield f"data: {json.dumps(sse_data)}\n\n"

                    last_seq = event.sequence_number

                    # Close on terminal state
                    if event.status in TERMINAL_TASK_STATUSES:
                        return

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
