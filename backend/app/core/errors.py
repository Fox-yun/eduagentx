"""Unified error handling for the API."""

from __future__ import annotations

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.common.schemas import ApiErrorBody, ApiErrorResponse

logger = structlog.get_logger()


class ApiError(Exception):
    """Application-level API error."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: object | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)


def _build_error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: object | None = None,
) -> JSONResponse:
    """Build a standardized error JSON response."""
    request_id = getattr(request.state, "request_id", None)
    body = ApiErrorResponse(
        error=ApiErrorBody(
            code=code,
            message=message,
            details=details,
            request_id=request_id,
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json"),
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register all error handlers on the FastAPI app."""

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        logger.warning("validation_error", path=request.url.path, errors=errors)
        return _build_error_response(
            request=request,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="VALIDATION_ERROR",
            message="Request validation failed",
            details=errors,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "HTTP_ERROR"
        message = str(exc.detail) if exc.detail else "An error occurred"
        return _build_error_response(
            request=request,
            status_code=exc.status_code,
            code=code,
            message=message,
        )

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        logger.warning("api_error", code=exc.code, message=exc.message, path=request.url.path)
        return _build_error_response(
            request=request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled_error", error=str(exc), path=request.url.path, exc_info=True)
        return _build_error_response(
            request=request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_ERROR",
            message="An internal error occurred",
        )
