"""Common Pydantic schemas shared across the application."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ApiErrorBody(BaseModel):
    """Error body within an API error response."""

    code: str
    message: str
    details: Any | None = None
    request_id: str | None = None


class ApiErrorResponse(BaseModel):
    """Unified error response envelope."""

    error: ApiErrorBody


class CursorPage[T](BaseModel):
    """Generic cursor-based pagination response."""

    items: list[T]
    next_cursor: str | None = None
    total: int | None = Field(default=None, ge=0)


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str = "3.0.0"
    environment: str = ""
