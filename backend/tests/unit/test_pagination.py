"""Tests for cursor pagination utilities."""

from __future__ import annotations

import pytest

from app.core.pagination import decode_cursor, encode_cursor


def test_encode_decode_roundtrip():
    data = {"order": "2026-06-24T12:00:00Z", "id": "abc-123"}
    encoded = encode_cursor(data)
    decoded = decode_cursor(encoded)
    assert decoded == data


def test_encode_produces_base64_string():
    data = {"order": "2026-06-24T12:00:00Z", "id": "abc-123"}
    encoded = encode_cursor(data)
    # Base64 URL-safe characters
    assert all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_=" for c in encoded)


def test_decode_invalid_cursor_raises():
    from app.core.errors import ApiError

    with pytest.raises(ApiError) as exc_info:
        decode_cursor("not-valid-base64!!!")
    assert exc_info.value.code == "INVALID_CURSOR"


def test_decode_empty_string_raises():
    from app.core.errors import ApiError

    with pytest.raises(ApiError):
        decode_cursor("")
