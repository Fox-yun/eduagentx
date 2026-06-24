"""Request ID middleware and context management."""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


def generate_request_id() -> str:
    """Generate a unique request ID."""
    return f"req_{uuid.uuid4().hex[:16]}"


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
