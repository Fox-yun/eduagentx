"""Integration tests for Email Verification & Resend Flow."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.outbox import OutboxEvent
from app.models.user import User, VerificationToken
from app.services.auth import AuthService
from app.services.email import decrypt_email_payload


async def test_register_creates_verification_token_and_outbox(db_session) -> None:
    unique_email = f"verify_{uuid.uuid4().hex[:8]}@example.com"
    service = AuthService(db_session)
    result = await service.register(
        email=unique_email,
        password="Password123!",
        display_name="Verify User",
    )

    assert result["next_step"] == "verify_email"
    raw_token = result["verification_token"]
    assert raw_token is not None

    # Verify outbox event created
    user_res = await db_session.execute(select(User).where(User.email == unique_email))
    user = user_res.scalar_one()

    outbox_res = await db_session.execute(
        select(OutboxEvent).where(
            OutboxEvent.aggregate_id == user.id,
            OutboxEvent.event_type == "email.verification.send",
        )
    )
    outbox = outbox_res.scalar_one_or_none()
    assert outbox is not None
    decrypted = decrypt_email_payload(outbox.payload["encrypted_data"])
    assert decrypted["token"] == raw_token


async def test_resend_verification_creates_new_token(db_session) -> None:
    unique_email = f"resend_{uuid.uuid4().hex[:8]}@example.com"
    service = AuthService(db_session)
    await service.register(
        email=unique_email,
        password="Password123!",
        display_name="Resend User",
    )
    user_res = await db_session.execute(select(User).where(User.email == unique_email))
    user = user_res.scalar_one()

    # Resend verification
    resend_res = await service.resend_verification(user_id=user.id)
    assert "sent" in resend_res["message"]

    # Check old tokens invalidated
    tokens_res = await db_session.execute(
        select(VerificationToken).where(
            VerificationToken.user_id == user.id,
            VerificationToken.purpose == "email_verification",
        )
    )
    tokens = list(tokens_res.scalars().all())
    assert len(tokens) == 2
    used_count = sum(1 for t in tokens if t.used_at is not None)
    assert used_count == 1
