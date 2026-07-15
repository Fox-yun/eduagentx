"""Cookie management for authentication tokens."""

from __future__ import annotations

from fastapi import Response
from fastapi.responses import JSONResponse

from app.config import get_settings

# Cookie names — not passwords, false positive from Bandit B105
ACCESS_TOKEN_COOKIE = "access_token"  # nosec B105
REFRESH_TOKEN_COOKIE = "refresh_token"  # nosec B105
CSRF_TOKEN_COOKIE = "csrftoken"  # nosec B105

# Cookie paths — not passwords, false positive from Bandit B105
ACCESS_TOKEN_PATH = "/"  # nosec B105
REFRESH_TOKEN_PATH = "/api/auth"  # nosec B105
CSRF_TOKEN_PATH = "/"  # nosec B105


def set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
    csrf_token: str,
) -> None:
    """Set all authentication cookies on the response."""
    settings = get_settings()

    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=access_token,
        max_age=settings.access_token_ttl_seconds,
        path=ACCESS_TOKEN_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain,
    )

    response.set_cookie(
        key=REFRESH_TOKEN_COOKIE,
        value=refresh_token,
        max_age=settings.refresh_token_ttl_seconds,
        path=REFRESH_TOKEN_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain,
    )

    response.set_cookie(
        key=CSRF_TOKEN_COOKIE,
        value=csrf_token,
        max_age=settings.refresh_token_ttl_seconds,
        path=CSRF_TOKEN_PATH,
        httponly=False,  # JavaScript needs to read this
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain,
    )


def clear_auth_cookies(response: Response) -> None:
    """Clear all authentication cookies."""
    settings = get_settings()

    response.delete_cookie(
        key=ACCESS_TOKEN_COOKIE,
        path=ACCESS_TOKEN_PATH,
        domain=settings.cookie_domain,
    )

    response.delete_cookie(
        key=REFRESH_TOKEN_COOKIE,
        path=REFRESH_TOKEN_PATH,
        domain=settings.cookie_domain,
    )

    response.delete_cookie(
        key=CSRF_TOKEN_COOKIE,
        path=CSRF_TOKEN_PATH,
        domain=settings.cookie_domain,
    )


def create_auth_response(
    access_token: str,
    refresh_token: str,
    csrf_token: str,
    body: dict[str, object] | None = None,
) -> JSONResponse:
    """Create a JSON response with authentication cookies set."""
    response = JSONResponse(content=body or {})
    set_auth_cookies(response, access_token, refresh_token, csrf_token)
    return response
