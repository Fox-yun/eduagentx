"""Tests for the shared OutboxDispatcher."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.outbox import OutboxEvent


def _make_event(**overrides: object) -> MagicMock:
    """Create a mock OutboxEvent compatible with flag_modified."""
    attrs = {
        "id": "test-event-001",
        "event_type": "task.execute",
        "payload": {},
        "status": "pending",
        "attempt_count": 0,
        "last_error": None,
        **overrides,
    }
    mock = MagicMock(spec=OutboxEvent, **{k: v for k, v in attrs.items() if k != "_sa_instance_state"})
    mock._sa_instance_state = MagicMock()
    return mock


@pytest.fixture
def fixed_now() -> datetime:
    return datetime(2026, 6, 29, 12, 0, 0, tzinfo=UTC)


class TestDispatchEvent:
    """Test dispatch_event routing and error handling."""

    @pytest.mark.asyncio
    async def test_task_execute_success(self, fixed_now: datetime) -> None:
        """task.execute event calls execute_task callback and marks published."""
        from app.workers.outbox_dispatcher import dispatch_event

        event = _make_event(payload={"task_id": "task-123", "task_type": "learning_path_generation"})
        execute_task = AsyncMock()

        result = await dispatch_event(event, event.payload, fixed_now, execute_task=execute_task)

        assert result is True
        assert event.status == "published"
        assert event.published_at == fixed_now
        execute_task.assert_awaited_once_with("task-123")

    @pytest.mark.asyncio
    async def test_task_execute_no_callback(self, fixed_now: datetime) -> None:
        """task.execute still marks published without execute_task callback."""
        from app.workers.outbox_dispatcher import dispatch_event

        event = _make_event(payload={"task_id": "task-123"})

        result = await dispatch_event(event, event.payload, fixed_now)

        assert result is True
        assert event.status == "published"

    @pytest.mark.asyncio
    async def test_task_execute_missing_task_id(self, fixed_now: datetime) -> None:
        """task.execute with no task_id in payload sets failed status."""
        from app.workers.outbox_dispatcher import dispatch_event

        event = _make_event(payload={"task_type": "learning_path_generation"})  # no task_id

        result = await dispatch_event(event, event.payload, fixed_now)

        assert result is False
        assert event.status == "failed"
        assert "missing task_id" in (event.last_error or "")

    @pytest.mark.asyncio
    async def test_email_verification_send(self, fixed_now: datetime) -> None:
        """email.verification.send dispatches via EmailService."""
        from app.workers.outbox_dispatcher import dispatch_event

        event = _make_event(
            id="test-email-001",
            event_type="email.verification.send",
            payload={
                "encrypted_data": "gAAAAABnq9NQ...",
                "recipient": "test@example.com",
                "to_name": "Test User",
            },
        )

        email_service_mock = AsyncMock()

        with (
            patch("app.services.email.decrypt_email_payload", return_value={"token": "verify-token-123"}),
            patch("app.services.email.EmailService", return_value=email_service_mock),
        ):
            result = await dispatch_event(event, event.payload, fixed_now)

        assert result is True
        assert event.status == "published"
        assert event.published_at == fixed_now
        email_service_mock.send_verification_email.assert_awaited_once_with(
            "test@example.com",
            "verify-token-123",
            "Test User",
            message_id="<outbox-test-email-001@eduagentx.local>",
        )
        # Verify sensitive data was cleared
        assert event.payload["encrypted_data"] is None

    @pytest.mark.asyncio
    async def test_email_password_reset_send(self, fixed_now: datetime) -> None:
        """email.password_reset.send dispatches via EmailService."""
        from app.workers.outbox_dispatcher import dispatch_event

        event = _make_event(
            id="test-reset-001",
            event_type="email.password_reset.send",
            payload={
                "encrypted_data": "gAAAAABnq9NQ...",
                "recipient": "reset@example.com",
                "to_name": None,
            },
        )

        email_service_mock = AsyncMock()

        with (
            patch("app.services.email.decrypt_email_payload", return_value={"token": "reset-token-456"}),
            patch("app.services.email.EmailService", return_value=email_service_mock),
        ):
            result = await dispatch_event(event, event.payload, fixed_now)

        assert result is True
        assert event.status == "published"
        email_service_mock.send_password_reset_email.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_email_no_token_does_not_crash(self, fixed_now: datetime) -> None:
        """Email event with missing token does not raise."""
        from app.workers.outbox_dispatcher import dispatch_event

        event = _make_event(
            event_type="email.verification.send",
            payload={
                "encrypted_data": "gAAAAABnq9NQ...",
                "recipient": "test@example.com",
                "to_name": None,
            },
        )

        email_service_mock = AsyncMock()

        with (
            patch("app.services.email.decrypt_email_payload", return_value={"token": None}),
            patch("app.services.email.EmailService", return_value=email_service_mock),
        ):
            result = await dispatch_event(event, event.payload, fixed_now)

        assert result is True
        email_service_mock.send_verification_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_email_missing_encrypted_data(self, fixed_now: datetime) -> None:
        """Email event with missing encrypted_data does not raise."""
        from app.workers.outbox_dispatcher import dispatch_event

        event = _make_event(
            event_type="email.verification.send",
            payload={"recipient": "test@example.com"},
        )

        email_service_mock = AsyncMock()

        with patch("app.services.email.EmailService", return_value=email_service_mock):
            result = await dispatch_event(event, event.payload, fixed_now)

        assert result is True
        email_service_mock.send_verification_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_unknown_event_type(self, fixed_now: datetime) -> None:
        """Unknown event type is published with a warning, not failed."""
        from app.workers.outbox_dispatcher import dispatch_event

        event = _make_event(event_type="unknown.event.type")

        result = await dispatch_event(event, {}, fixed_now)

        assert result is True
        assert event.status == "published"
