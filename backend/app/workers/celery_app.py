"""Celery application configuration."""

from __future__ import annotations

from celery import Celery  # type: ignore[import-not-found]

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "eduagentx",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=300,
    task_time_limit=600,
    task_default_retry_delay=60,
    task_max_retries=3,
)

# Auto-discover tasks in worker modules
celery_app.autodiscover_tasks(["app.workers"])
