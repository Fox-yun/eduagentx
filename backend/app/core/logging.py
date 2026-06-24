"""Structured logging configuration."""

from __future__ import annotations

import logging

import structlog

from app.config import get_settings


def setup_logging() -> None:
    """Configure structured logging with structlog."""
    settings = get_settings()

    # Set log level
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.getLogger().setLevel(log_level)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer() if settings.is_production else structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
