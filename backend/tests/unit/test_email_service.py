"""Unit tests for EmailService, Transport, and Payload Encryption."""

from __future__ import annotations

import pytest

from app.services.email import (
    EmailMessageData,
    EmailService,
    decrypt_email_payload,
    encrypt_email_payload,
)


class FakeEmailTransport:
    def __init__(self) -> None:
        self.sent_messages: list[EmailMessageData] = []

    async def send(self, message: EmailMessageData) -> None:
        self.sent_messages.append(message)


def test_payload_encryption_decryption() -> None:
    payload = {"token": "secret-token-123", "user_id": "user-uuid-456"}
    encrypted = encrypt_email_payload(payload)
    assert encrypted != "secret-token-123"

    decrypted = decrypt_email_payload(encrypted)
    assert decrypted == payload


@pytest.mark.asyncio
async def test_send_verification_email() -> None:
    transport = FakeEmailTransport()
    service = EmailService(transport=transport)

    await service.send_verification_email(
        to_email="test@example.com",
        raw_token="token-abc",
        to_name="Test User",
    )

    assert len(transport.sent_messages) == 1
    msg = transport.sent_messages[0]
    assert msg.to_email == "test@example.com"
    assert msg.to_name == "Test User"
    assert "验证您的电子邮箱" in msg.subject
    assert "token-abc" in msg.text_body
    assert "token-abc" in msg.html_body


@pytest.mark.asyncio
async def test_send_password_reset_email() -> None:
    transport = FakeEmailTransport()
    service = EmailService(transport=transport)

    await service.send_password_reset_email(
        to_email="reset@example.com",
        raw_token="reset-token-xyz",
        to_name="Reset User",
    )

    assert len(transport.sent_messages) == 1
    msg = transport.sent_messages[0]
    assert msg.to_email == "reset@example.com"
    assert msg.to_name == "Reset User"
    assert "重置您的密码" in msg.subject
    assert "reset-token-xyz" in msg.text_body
    assert "reset-token-xyz" in msg.html_body
