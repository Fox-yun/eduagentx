"""Security utilities: password hashing, JWT tokens, CSRF."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jwt.exceptions import PyJWTError

from app.config import get_settings
from app.core.errors import ApiError

# Password hasher with Argon2id
_ph = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)

# Common weak passwords to block
WEAK_PASSWORDS: frozenset[str] = frozenset(
    {
        "password",
        "123456789",
        "1234567890",
        "qwerty1234",
        "abc123456",
        "password123",
        "admin12345",
        "letmein1234",
        "welcome123",
        "monkey1234",
    }
)


def hash_password(password: str) -> str:
    """Hash a password using Argon2id."""
    return _ph.hash(password)


def verify_password(password: str, hash_value: str) -> bool:
    """Verify a password against its hash."""
    try:
        return _ph.verify(hash_value, password)
    except VerifyMismatchError:
        return False


def needs_rehash(hash_value: str) -> bool:
    """Check if a password hash needs to be rehashed."""
    return _ph.check_needs_rehash(hash_value)


def validate_password_strength(password: str) -> None:
    """Validate password meets requirements."""
    if len(password) < 10:
        raise ApiError(code="WEAK_PASSWORD", message="Password must be at least 10 characters", status_code=400)
    if len(password) > 128:
        raise ApiError(code="WEAK_PASSWORD", message="Password must be at most 128 characters", status_code=400)
    if password.lower() in WEAK_PASSWORDS:
        raise ApiError(code="WEAK_PASSWORD", message="This password is too common", status_code=400)


def normalize_email(email: str) -> str:
    """Normalize email for consistent storage and comparison."""
    local, domain = email.lower().strip().rsplit("@", 1)
    # Gmail-specific normalization: remove dots and plus aliases
    if domain in ("gmail.com", "googlemail.com"):
        local = local.split("+")[0].replace(".", "")
    return f"{local}@{domain}"


def generate_token() -> str:
    """Generate a cryptographically secure random token."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Hash a token for storage (using SHA-256)."""
    return hashlib.sha256(token.encode()).hexdigest()


def generate_jti() -> str:
    """Generate a unique JWT ID."""
    return str(uuid.uuid4())


def create_access_token(user_id: str, session_id: str) -> str:
    """Create a signed JWT access token.

    Payload includes:
    - sub: user ID
    - sid: session ID
    - jti: unique token ID for tracking
    - iat: issued at time
    - exp: expiration time
    - type: token type (access)
    """
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "sid": session_id,
        "jti": generate_jti(),
        "iat": now,
        "exp": now + timedelta(seconds=settings.access_token_ttl_seconds),
        "type": "access",
    }
    return jwt.encode(payload, settings.app_secret_key, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, object]:
    """Decode and verify an access token."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.app_secret_key, algorithms=["HS256"])
        if payload.get("type") != "access":
            raise ApiError(code="INVALID_TOKEN", message="Invalid token type", status_code=401)
        return payload
    except PyJWTError as e:
        raise ApiError(code="INVALID_TOKEN", message="Invalid or expired token", status_code=401) from e


def generate_csrf_token() -> str:
    """Generate a CSRF token."""
    return secrets.token_urlsafe(32)


def constant_time_compare(a: str, b: str) -> bool:
    """Compare two strings in constant time to prevent timing attacks."""
    return hmac.compare_digest(a.encode(), b.encode())
