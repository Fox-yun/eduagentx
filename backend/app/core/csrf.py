"""CSRF protection middleware."""

from __future__ import annotations

import hmac

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import get_settings
from app.core.request_context import generate_request_id

# Paths exempt from CSRF checking
CSRF_EXEMPT_PATHS: frozenset[str] = frozenset(
    {
        "/api/auth/csrf",
        "/api/auth/register",
        "/api/auth/login",
        "/api/auth/verify-email",
        "/api/auth/resend-verification",
        "/api/auth/forgot-password",
        "/api/auth/reset-password",
        "/health/live",
        "/health/ready",
        "/docs",
        "/redoc",
        "/openapi.json",
    }
)

# Unsafe methods that require CSRF tokens
CSRF_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class CSRFMiddleware(BaseHTTPMiddleware):
    """CSRF protection using Double Submit Cookie pattern.

    For unsafe methods (POST, PUT, PATCH, DELETE):
    - Reads the CSRF token from the cookie
    - Reads the CSRF token from the X-CSRF-Token header
    - Compares them using constant-time comparison
    - Rejects the request if they don't match
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        settings = get_settings()

        # Skip CSRF check for safe methods
        if request.method not in CSRF_METHODS:
            return await call_next(request)

        # Skip CSRF check for exempt paths
        if request.url.path in CSRF_EXEMPT_PATHS:
            return await call_next(request)

        # Skip if path starts with exempt prefixes
        if request.url.path.startswith("/health"):
            return await call_next(request)

        # Skip E2E test routes (protected by X-E2E-Token instead)
        # Only exempt when E2E routes are actually enabled
        is_e2e_request = (
            settings.app_env == "test" and settings.enable_e2e_routes and request.url.path.startswith("/api/__e2e__/")
        )
        if is_e2e_request:
            return await call_next(request)

        # Get CSRF token from cookie
        csrf_cookie = request.cookies.get(settings.csrf_cookie_name, "")
        csrf_header = request.headers.get(settings.csrf_header_name, "")

        # Both must be present and match
        if not csrf_cookie or not csrf_header:
            request_id = getattr(request.state, "request_id", generate_request_id())
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "CSRF_ERROR",
                        "message": "CSRF token missing",
                        "request_id": request_id,
                    }
                },
            )

        if not hmac.compare_digest(csrf_cookie, csrf_header):
            request_id = getattr(request.state, "request_id", generate_request_id())
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "CSRF_ERROR",
                        "message": "CSRF token mismatch",
                        "request_id": request_id,
                    }
                },
            )

        return await call_next(request)
