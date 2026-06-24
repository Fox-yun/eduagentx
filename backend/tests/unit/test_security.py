"""Tests for security utilities."""

from __future__ import annotations

import pytest

from app.core.errors import ApiError
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_csrf_token,
    generate_token,
    hash_password,
    hash_token,
    needs_rehash,
    normalize_email,
    validate_password_strength,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_and_verify(self):
        password = "SecureP@ss123"
        hash_value = hash_password(password)
        assert verify_password(password, hash_value)

    def test_wrong_password_fails(self):
        password = "SecureP@ss123"
        hash_value = hash_password(password)
        assert not verify_password("WrongPassword", hash_value)

    def test_needs_rehash(self):
        hash_value = hash_password("test")
        assert not needs_rehash(hash_value)


class TestPasswordValidation:
    def test_valid_password(self):
        validate_password_strength("SecureP@ss123")  # Should not raise

    def test_too_short(self):
        with pytest.raises(ApiError) as exc_info:
            validate_password_strength("short")
        assert exc_info.value.code == "WEAK_PASSWORD"

    def test_too_long(self):
        with pytest.raises(ApiError):
            validate_password_strength("a" * 129)

    def test_common_password(self):
        with pytest.raises(ApiError):
            validate_password_strength("password123")


class TestEmailNormalization:
    def test_lowercase(self):
        assert normalize_email("User@Example.COM") == "user@example.com"

    def test_gmail_dots(self):
        assert normalize_email("u.s.e.r@gmail.com") == "user@gmail.com"

    def test_gmail_plus(self):
        assert normalize_email("user+tag@gmail.com") == "user@gmail.com"


class TestTokens:
    def test_generate_token(self):
        token = generate_token()
        assert len(token) > 20

    def test_hash_token(self):
        token = "test-token"
        hash1 = hash_token(token)
        hash2 = hash_token(token)
        assert hash1 == hash2

    def test_generate_csrf(self):
        csrf = generate_csrf_token()
        assert len(csrf) > 20


class TestJWT:
    def test_create_and_decode(self):
        token = create_access_token("user-123", "session-456")
        payload = decode_access_token(token)
        assert payload["sub"] == "user-123"
        assert payload["sid"] == "session-456"
        assert payload["type"] == "access"

    def test_invalid_token(self):
        with pytest.raises(ApiError) as exc_info:
            decode_access_token("invalid-token")
        assert exc_info.value.code == "INVALID_TOKEN"
