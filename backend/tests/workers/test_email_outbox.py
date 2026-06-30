"""Unit and Worker tests for Outbox Email dispatching and failure handling."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from app.models.outbox import OutboxEvent
from app.services.email import EmailDeliveryError, encrypt_email_payload
from app.workers.outbox_publisher import publish_pending_outbox


class MockFailingTransport:
    async def send(self, message) -> None:
        raise EmailDeliveryError("Connection refused by SMTP server")


class MockSuccessTransport:
    def __init__(self) -> None:
        self.sent = []

    async def send(self, message) -> None:
        self.sent.append(message)


def _bind_outbox_factory(db_session, monkeypatch):
    @asynccontextmanager
    async def mock_cm():
        yield db_session

    monkeypatch.setattr("app.workers.outbox_publisher.get_session_factory", lambda: mock_cm)


def _make_event_id(prefix: str) -> str:
    return f"outbox_{prefix}_{uuid.uuid4().hex[:8]}"


async def test_email_outbox_failure_retains_encrypted_payload(db_session, monkeypatch) -> None:
    """Test that SMTP failures retain sensitive_payload and increment attempt count."""
    _bind_outbox_factory(db_session, monkeypatch)

    # Patch transport on EmailService to fail
    monkeypatch.setattr(
        "app.services.email.SmtpEmailTransport",
        lambda: MockFailingTransport(),
    )

    event_id = _make_event_id("fail")
    raw_token = "fail-token-123"
    enc_payload = encrypt_email_payload({"token": raw_token, "user_id": "user-fail-id"})

    event = OutboxEvent(
        id=event_id,
        event_type="email.verification.send",
        aggregate_type="User",
        aggregate_id="user-fail-id",
        payload={
            "recipient": "fail@example.com",
            "to_name": "Fail User",
            "encrypted_data": enc_payload,
        },
        status="pending",
        attempt_count=0,
    )
    db_session.add(event)
    await db_session.commit()

    # Publish pending outbox
    await publish_pending_outbox()

    # Refresh event from DB
    await db_session.refresh(event)
    assert event.status == "pending"
    assert event.attempt_count == 1
    assert event.last_error is not None
    assert "SMTP server" in event.last_error
    # Encrypted payload MUST be retained on failure for retries
    assert event.payload["encrypted_data"] == enc_payload


async def test_email_outbox_success_clears_encrypted_payload(db_session, monkeypatch) -> None:
    """Test that SMTP success marks event published and clears sensitive encrypted payload."""
    _bind_outbox_factory(db_session, monkeypatch)

    success_transport = MockSuccessTransport()
    monkeypatch.setattr(
        "app.services.email.SmtpEmailTransport",
        lambda: success_transport,
    )

    event_id = _make_event_id("success")
    raw_token = "success-token-456"
    enc_payload = encrypt_email_payload({"token": raw_token, "user_id": "user-success-id"})

    event = OutboxEvent(
        id=event_id,
        event_type="email.password_reset.send",
        aggregate_type="User",
        aggregate_id="user-success-id",
        payload={
            "recipient": "success@example.com",
            "to_name": "Success User",
            "encrypted_data": enc_payload,
        },
        status="pending",
        attempt_count=0,
    )
    db_session.add(event)
    await db_session.commit()

    # Reset any leftover events from previous tests — only process our event
    from sqlalchemy import update as sa_update

    await db_session.execute(
        sa_update(OutboxEvent)
        .where(OutboxEvent.id != event_id, OutboxEvent.status == "pending")
        .values(status="failed")
    )
    await db_session.commit()

    # Publish pending outbox
    await publish_pending_outbox()

    # Refresh event from DB
    await db_session.refresh(event)
    assert event.status == "published"
    assert event.published_at is not None
    assert event.payload["encrypted_data"] is None
    assert len(success_transport.sent) == 1
    assert success_transport.sent[0].message_id == f"<outbox-{event_id}@eduagentx.local>"
