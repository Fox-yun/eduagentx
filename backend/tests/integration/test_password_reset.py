"""Integration tests for Password Reset & Session Revocation."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.errors import ApiError
from app.models.outbox import OutboxEvent
from app.models.user import AuthSession, User
from app.services.auth import AuthService
from app.services.email import decrypt_email_payload


async def test_forgot_password_and_reset_flow(db_session) -> None:
    unique_email = f"pwreset_{uuid.uuid4().hex[:8]}@example.com"
    service = AuthService(db_session)
    # Register and auto-activate user
    await service.register(
        email=unique_email,
        password="OldPassword123!",
        display_name="Reset User",
    )
    user_res = await db_session.execute(select(User).where(User.email == unique_email))
    user = user_res.scalar_one()
    user.email_verified_at = user.created_at
    user.status = "active"
    await db_session.commit()

    # Login to create an active session
    login_res = await service.login(email=unique_email, password="OldPassword123!")
    session_id = login_res["session"].id

    # Forgot password request
    req_res = await service.request_password_reset(email=unique_email)
    assert "sent" in req_res["message"]

    # Retrieve reset token from outbox
    outbox_res = await db_session.execute(
        select(OutboxEvent).where(
            OutboxEvent.aggregate_id == user.id,
            OutboxEvent.event_type == "email.password_reset.send",
        )
    )
    outbox = outbox_res.scalar_one()
    decrypted = decrypt_email_payload(outbox.payload["encrypted_data"])
    reset_token = decrypted["token"]

    # Perform reset password
    await service.reset_password(token=reset_token, new_password="NewPassword456!")

    # Verify session revoked
    sess_res = await db_session.execute(select(AuthSession).where(AuthSession.id == session_id))
    sess = sess_res.scalar_one()
    assert sess.revoked_at is not None
    assert sess.revoke_reason == "password_reset"

    # Verify old password login fails
    with pytest.raises(ApiError):
        await service.login(email=unique_email, password="OldPassword123!")

    # Verify new password login succeeds
    new_login = await service.login(email=unique_email, password="NewPassword456!")
    assert new_login["user"].id == user.id
