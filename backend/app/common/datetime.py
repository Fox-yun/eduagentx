"""DateTime utilities for consistent ISO 8601 handling."""

from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Get current UTC time with timezone info."""
    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    """Ensure a datetime is timezone-aware and in UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def to_iso_string(dt: datetime | None) -> str | None:
    """Convert datetime to ISO 8601 string with timezone offset."""
    if dt is None:
        return None
    dt = ensure_utc(dt)
    return dt.isoformat()
