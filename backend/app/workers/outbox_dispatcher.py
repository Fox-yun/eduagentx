"""Shared outbox event dispatcher.

Provides a unified dispatch() method used by both the Celery-based
outbox publisher and the development-mode inline runner, eliminating
the duplicate dispatch logic that previously caused email events
to be silently dropped by the inline runner.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy.orm.attributes import flag_modified

from app.models.outbox import OutboxEvent

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from datetime import datetime

logger = structlog.get_logger()


class OutboxDispatchError(Exception):
    """Raised when an outbox event cannot be dispatched after all retries."""


async def dispatch_event(
    event: OutboxEvent,
    payload: dict[str, Any],
    now: datetime,
    *,
    execute_task: Callable[[str], Awaitable[None]] | None = None,
) -> bool:
    """Dispatch a single outbox event.

    Handles task.execute, email.verification.send, and
    email.password_reset.send event types.

    Args:
        event: The outbox event to dispatch (modified in-place).
        payload: Parsed event payload.
        now: Current timestamp for event.published_at.
        execute_task: Async callback for task execution (e.g. Celery
            .delay or inline create_task). If None, task.execute
            events are still published but not dispatched further
            (caller is responsible for worker pickup).

    Returns:
        True if the event was handled successfully. The event's
        status and published_at are set in-place.

    Raises:
        OutboxDispatchError: On permanent dispatch failure.
    """
    event_type = event.event_type

    if event_type == "task.execute":
        return await _dispatch_task_execute(event, payload, now, execute_task=execute_task)
    elif event_type in ("email.verification.send", "email.password_reset.send"):
        return await _dispatch_email(event, payload, now)
    else:
        logger.warning(
            "unknown_event_type",
            event_id=event.id,
            event_type=event_type,
            aggregate_type=event.aggregate_type,
        )
        event.status = "published"
        event.published_at = now
        return True


async def _dispatch_task_execute(
    event: OutboxEvent,
    payload: dict[str, Any],
    now: datetime,
    *,
    execute_task: Callable[[str], Awaitable[None]] | None,
) -> bool:
    """Dispatch a task.execute event."""
    task_id = payload.get("task_id")
    if not task_id:
        logger.error("task_execute_missing_task_id", event_id=event.id)
        event.status = "failed"
        event.last_error = "task.execute event missing task_id in payload"
        return False

    event.status = "published"
    event.published_at = now
    logger.info("task_outbox_dispatched", event_id=event.id, task_id=task_id, task_type=payload.get("task_type"))

    if execute_task is not None:
        await execute_task(task_id)

    return True


async def _dispatch_email(
    event: OutboxEvent,
    payload: dict[str, Any],
    now: datetime,
) -> bool:
    """Dispatch an email event via SMTP."""
    from app.services.email import EmailService, decrypt_email_payload

    encrypted_data = payload.get("encrypted_data")
    recipient = payload.get("recipient")
    to_name = payload.get("to_name")

    if encrypted_data and recipient:
        decrypted = decrypt_email_payload(encrypted_data)
        raw_token = decrypted.get("token")
        if raw_token:
            email_service = EmailService()
            msg_id = f"<outbox-{event.id}@eduagentx.local>"
            if event.event_type == "email.verification.send":
                await email_service.send_verification_email(recipient, raw_token, to_name, message_id=msg_id)
            else:
                await email_service.send_password_reset_email(recipient, raw_token, to_name, message_id=msg_id)
        else:
            logger.warning("email_payload_missing_token", event_id=event.id, recipient=recipient)
    else:
        logger.warning("email_payload_missing_data", event_id=event.id, recipient=recipient)

    # Clear sensitive data from payload
    new_payload = dict(payload)
    new_payload["encrypted_data"] = None
    event.payload = new_payload
    flag_modified(event, "payload")

    event.status = "published"
    event.published_at = now
    logger.info("email_outbox_dispatched", event_id=event.id, event_type=event.event_type)

    return True
