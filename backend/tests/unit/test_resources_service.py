from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.unit import LearningResource
from app.services.resources import RESOURCE_TYPES, ResourceService


@pytest.mark.asyncio
async def test_failed_resource_retry_uses_new_idempotency_key() -> None:
    resource = MagicMock(spec=LearningResource)
    resource.id = "resource-1"
    resource.status = "failed"
    resource.active_task_id = None
    resource.error_code = "GENERATION_ERROR"
    resource.error_message = "network unavailable"

    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = resource
    db = MagicMock()
    db.execute = AsyncMock(return_value=scalar_result)
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    task = SimpleNamespace(id="task-retry-1")

    with patch("app.services.task.TaskService.enqueue_task", new=AsyncMock(return_value=task)) as enqueue:
        result = await ResourceService(db).get_or_create_resource(
            "path-1",
            "node-1",
            "user-1",
            "narrated_video",
        )

    idempotency_key = enqueue.await_args.kwargs["idempotency_key"]
    assert idempotency_key.startswith("resource-generate:user-1:node-1:narrated_video:retry:")
    assert result["active_task_id"] == "task-retry-1"
    assert resource.status == "generating"
    assert resource.error_code is None
    assert resource.error_message is None


@pytest.mark.asyncio
async def test_force_regeneration_replaces_a_ready_resource() -> None:
    resource = MagicMock(spec=LearningResource)
    resource.id = "resource-1"
    resource.status = "ready"
    resource.active_task_id = None
    resource.error_code = None
    resource.error_message = None
    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = resource
    db = MagicMock()
    db.execute = AsyncMock(return_value=scalar_result)
    db.commit = AsyncMock()
    task = SimpleNamespace(id="task-force-1")

    with patch("app.services.task.TaskService.enqueue_task", new=AsyncMock(return_value=task)) as enqueue:
        result = await ResourceService(db).get_or_create_resource(
            "path-1", "node-1", "user-1", "interactive_cards", force=True
        )

    assert enqueue.await_args.kwargs["idempotency_key"].startswith(
        "resource-generate:user-1:node-1:interactive_cards:retry:"
    )
    assert result["status"] == "generating"


@pytest.mark.asyncio
async def test_missing_ready_artifact_is_marked_for_regeneration() -> None:
    resource = MagicMock(spec=LearningResource)
    resource.id = "resource-1"
    resource.status = "ready"
    resource.active_task_id = None
    resource.storage_key = "resources/user/node/presentation.pptx"
    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = resource
    db = MagicMock()
    db.execute = AsyncMock(return_value=scalar_result)
    db.commit = AsyncMock()
    service = ResourceService(db)
    service.storage = AsyncMock()
    service.storage.exists = AsyncMock(return_value=False)

    result = await service.get_resource_content("path-1", "node-1", "user-1", "pptx")

    assert result["status"] == "failed"
    assert result["content"]["error_code"] == "RESOURCE_ARTIFACT_NOT_FOUND"
    assert resource.status == "failed"
    db.commit.assert_awaited_once()


def test_narrated_video_is_a_supported_resource_type() -> None:
    assert "narrated_video" in RESOURCE_TYPES
    assert "simulation" not in RESOURCE_TYPES
