"""Request ID middleware and context management."""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


def generate_request_id() -> str:
    """Generate a unique request ID."""
    return f"req_{uuid.uuid4().hex[:16]}"


def get_client_ip(request: Request) -> str | None:
    """Get the real client IP, respecting reverse proxy headers.

    Checks (in order):
    1. X-Forwarded-For (first IP, which is the original client)
    2. X-Real-IP
    3. request.client.host (direct connection)
    """
    # X-Forwarded-For: client, proxy1, proxy2
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    # X-Real-IP (common with nginx)
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    # Direct connection
    if request.client:
        return request.client.host

    return None


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware that ensures every request has a request ID.

    - Accepts a valid X-Request-ID header from the client.
    - Generates a new one if missing.
    - Stores it on request.state.
    - Adds it to the response header.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id")
        if not request_id or len(request_id) > 128:
            request_id = generate_request_id()

        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
