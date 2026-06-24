"""Authentication service with business logic."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.datetime import utc_now
from app.common.enums import UserStatus
from app.config import get_settings
from app.core.errors import ApiError
from app.core.security import (
    create_access_token,
    generate_csrf_token,
    generate_jti,
    generate_token,
    hash_password,
    hash_token,
    needs_rehash,
    normalize_email,
    validate_password_strength,
    verify_password,
)
from app.models.user import AuthAuditLog, AuthSession, RefreshToken, User, UserProfile, VerificationToken

logger = structlog.get_logger()


class AuthService:
    """Authentication business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def register(
        self,
        email: str,
        password: str,
        display_name: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        """Register a new user."""
        validate_password_strength(password)

        email_normalized = normalize_email(email)

        # Check for existing user
        existing = await self.db.execute(select(User).where(User.email_normalized == email_normalized))
        if existing.scalar_one_or_none():
            raise ApiError(code="EMAIL_EXISTS", message="An account with this email already exists", status_code=409)

        # Create user
        user = User(
            id=str(uuid.uuid4()),
            email=email.strip(),
            email_normalized=email_normalized,
            display_name=display_name.strip(),
            password_hash=hash_password(password),
            status=UserStatus.PENDING_VERIFICATION.value,
        )
        self.db.add(user)

        # Create profile
        profile = UserProfile(user_id=user.id)
        self.db.add(profile)

        # Create verification token
        token = generate_token()
        verification = VerificationToken(
            id=str(uuid.uuid4()),
            user_id=user.id,
            purpose="email_verification",
            token_hash=hash_token(token),
            expires_at=utc_now() + timedelta(hours=24),
        )
        self.db.add(verification)

        # Audit log
        self._add_audit_log(user.id, "register", ip_address, user_agent)

        await self.db.flush()

        return {
            "user": user,
            "verification_token": token,
            "next_step": "verify_email",
        }

    async def verify_email(self, token: str) -> User:
        """Verify a user's email address."""
        token_hash = hash_token(token)

        result = await self.db.execute(
            select(VerificationToken).where(
                VerificationToken.token_hash == token_hash,
                VerificationToken.purpose == "email_verification",
                VerificationToken.used_at.is_(None),
            )
        )
        verification = result.scalar_one_or_none()

        if not verification:
            raise ApiError(code="INVALID_TOKEN", message="Invalid or expired verification token", status_code=400)

        if verification.expires_at < utc_now():
            raise ApiError(code="TOKEN_EXPIRED", message="Verification token has expired", status_code=400)

        # Mark token as used
        verification.used_at = utc_now()

        # Update user
        user_result = await self.db.execute(select(User).where(User.id == verification.user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            raise ApiError(code="USER_NOT_FOUND", message="User not found", status_code=404)

        user.email_verified_at = utc_now()
        user.status = UserStatus.ACTIVE.value

        self._add_audit_log(user.id, "email_verified")
        await self.db.flush()

        return user

    async def login(
        self,
        email: str,
        password: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        """Authenticate a user and create a session."""
        email_normalized = normalize_email(email)

        result = await self.db.execute(select(User).where(User.email_normalized == email_normalized))
        user = result.scalar_one_or_none()

        if not user or not verify_password(password, user.password_hash):
            # Record failed attempt if user exists
            if user:
                user.failed_login_count += 1
                # Lock after 5 failures
                if user.failed_login_count >= 5:
                    user.locked_until = utc_now() + timedelta(minutes=15)
                    user.status = UserStatus.LOCKED.value
                    self._add_audit_log(user.id, "account_locked", ip_address, user_agent)
                self._add_audit_log(user.id, "login_failed", ip_address, user_agent)
            await self.db.flush()
            raise ApiError(code="INVALID_CREDENTIALS", message="Invalid email or password", status_code=401)

        # Check account status
        if user.status == UserStatus.LOCKED.value:
            if user.locked_until and user.locked_until > utc_now():
                raise ApiError(code="ACCOUNT_LOCKED", message="Account is temporarily locked", status_code=403)
            # Lock expired, unlock
            user.status = UserStatus.ACTIVE.value
            user.failed_login_count = 0
            user.locked_until = None

        if user.status == UserStatus.DISABLED.value:
            raise ApiError(code="ACCOUNT_DISABLED", message="Account is disabled", status_code=403)

        if user.status == UserStatus.DELETED.value:
            raise ApiError(code="INVALID_CREDENTIALS", message="Invalid email or password", status_code=401)

        # Reset failed login count
        user.failed_login_count = 0
        user.last_login_at = utc_now()

        # Rehash password if needed
        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)

        # Create session
        settings = get_settings()
        jti = generate_jti()
        family_id = str(uuid.uuid4())
        refresh_token = generate_token()

        session = AuthSession(
            id=str(uuid.uuid4()),
            user_id=user.id,
            refresh_token_hash=hash_token(refresh_token),
            refresh_token_jti=jti,
            token_family_id=family_id,
            user_agent=user_agent,
            ip_address=ip_address,
            expires_at=utc_now() + timedelta(seconds=settings.refresh_token_ttl_seconds),
        )
        self.db.add(session)

        # Create refresh token record
        now = utc_now()
        refresh_token_record = RefreshToken(
            id=str(uuid.uuid4()),
            session_id=session.id,
            token_family_id=family_id,
            token_hash=hash_token(refresh_token),
            jti=jti,
            issued_at=now,
            expires_at=now + timedelta(seconds=settings.refresh_token_ttl_seconds),
        )
        self.db.add(refresh_token_record)

        # Create tokens
        access_token = create_access_token(user.id, session.id)
        csrf_token = generate_csrf_token()

        self._add_audit_log(user.id, "login_success", ip_address, user_agent, session.id)
        await self.db.flush()

        return {
            "user": user,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "csrf_token": csrf_token,
            "session": session,
        }

    async def refresh(
        self,
        refresh_token: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        """Refresh an access token using a refresh token.

        Implements token rotation with reuse detection:
        1. Find the refresh token by hash
        2. Use SELECT FOR UPDATE to prevent concurrent rotation
        3. Check if token has been used (reuse detection)
        4. Mark current token as used
        5. Create new refresh token
        6. Return new access and refresh tokens
        """
        settings = get_settings()
        token_hash = hash_token(refresh_token)

        # Find refresh token with FOR UPDATE lock to prevent concurrent rotation
        result = await self.db.execute(
            select(RefreshToken)
            .where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked_at.is_(None),
            )
            .with_for_update()
        )
        token_record = result.scalar_one_or_none()

        if not token_record:
            # Token not found - could be invalid or already revoked
            raise ApiError(code="INVALID_TOKEN", message="Invalid refresh token", status_code=401)

        # Check expiration
        if token_record.expires_at < utc_now():
            raise ApiError(code="TOKEN_EXPIRED", message="Refresh token has expired", status_code=401)

        # Check for reuse detection - if token was already used, it's a reuse attack
        if token_record.used_at is not None:
            # Token reuse detected! Revoke entire token family
            await self._handle_token_reuse(token_record)
            raise ApiError(code="REFRESH_TOKEN_REUSE", message="Token reuse detected", status_code=401)

        # Get the session
        session_result = await self.db.execute(
            select(AuthSession).where(
                AuthSession.id == token_record.session_id,
                AuthSession.revoked_at.is_(None),
            )
        )
        session = session_result.scalar_one_or_none()

        if not session:
            raise ApiError(code="SESSION_REVOKED", message="Session has been revoked", status_code=401)

        # Mark current token as used
        token_record.used_at = utc_now()

        # Create new refresh token
        new_jti = generate_jti()
        new_refresh_token = generate_token()
        now = utc_now()

        new_token_record = RefreshToken(
            id=str(uuid.uuid4()),
            session_id=session.id,
            token_family_id=token_record.token_family_id,
            token_hash=hash_token(new_refresh_token),
            jti=new_jti,
            parent_jti=token_record.jti,
            issued_at=now,
            expires_at=now + timedelta(seconds=settings.refresh_token_ttl_seconds),
        )
        self.db.add(new_token_record)

        # Update the old token's replaced_by_jti
        token_record.replaced_by_jti = new_jti

        # Update session
        session.refresh_token_hash = hash_token(new_refresh_token)
        session.refresh_token_jti = new_jti
        session.last_used_at = utc_now()
        session.ip_address = ip_address
        session.user_agent = user_agent

        # Create new access token
        access_token = create_access_token(session.user_id, session.id)
        csrf_token = generate_csrf_token()

        self._add_audit_log(session.user_id, "refresh", ip_address, user_agent, session.id)
        await self.db.flush()

        return {
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "csrf_token": csrf_token,
        }

    async def logout(
        self,
        session_id: str,
        user_id: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """Logout by revoking the current session and all its refresh tokens."""
        result = await self.db.execute(
            select(AuthSession).where(
                AuthSession.id == session_id,
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
            )
        )
        session = result.scalar_one_or_none()

        if session:
            now = utc_now()

            # Revoke all refresh tokens for this session
            await self.db.execute(
                update(RefreshToken)
                .where(
                    RefreshToken.session_id == session_id,
                    RefreshToken.revoked_at.is_(None),
                )
                .values(revoked_at=now, revoke_reason="logout")
            )

            # Revoke the session
            session.revoked_at = now
            session.revoke_reason = "logout"
            self._add_audit_log(user_id, "logout", ip_address, user_agent, session_id)
            await self.db.flush()

    async def logout_all(
        self,
        user_id: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """Logout from all sessions by revoking all sessions and refresh tokens."""
        now = utc_now()

        # Get all active session IDs for the user
        sessions_result = await self.db.execute(
            select(AuthSession.id).where(
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
            )
        )
        session_ids = [row[0] for row in sessions_result.all()]

        if session_ids:
            # Revoke all refresh tokens for these sessions
            await self.db.execute(
                update(RefreshToken)
                .where(
                    RefreshToken.session_id.in_(session_ids),
                    RefreshToken.revoked_at.is_(None),
                )
                .values(revoked_at=now, revoke_reason="logout_all")
            )

        # Revoke all sessions
        await self.db.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now, revoke_reason="logout_all")
        )
        self._add_audit_log(user_id, "logout_all", ip_address, user_agent)
        await self.db.flush()

    async def _handle_token_reuse(self, token_record: RefreshToken) -> None:
        """Handle detected token reuse by revoking the entire token family.

        When token reuse is detected:
        1. Revoke all refresh tokens in the same family
        2. Revoke the associated session
        3. Log the security event
        """
        now = utc_now()

        # Revoke all refresh tokens in the family
        await self.db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.token_family_id == token_record.token_family_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now, revoke_reason="reuse_detected")
        )

        # Revoke the session
        await self.db.execute(
            update(AuthSession)
            .where(
                AuthSession.id == token_record.session_id,
                AuthSession.revoked_at.is_(None),
            )
            .values(revoked_at=now, revoke_reason="reuse_detected")
        )

        self._add_audit_log(None, "refresh_reuse_detected", details=f"token_family={token_record.token_family_id}")
        await self.db.flush()

    def _add_audit_log(
        self,
        user_id: str | None,
        event_type: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        session_id: str | None = None,
        details: str | None = None,
    ) -> None:
        """Add an audit log entry."""
        log = AuthAuditLog(
            id=str(uuid.uuid4()),
            user_id=user_id,
            event_type=event_type,
            ip_address=ip_address,
            user_agent=user_agent,
            session_id=session_id,
            details=details,
        )
        self.db.add(log)
