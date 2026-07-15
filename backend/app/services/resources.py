"""Multimodal learning resource generation service.

Manages creation and retrieval of PPTX, Code ZIP, and Interactive resources.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.datetime import utc_now
from app.core.errors import ApiError
from app.models.unit import LearningResource, LearningUnitContent
from app.services.storage import ObjectStorage, get_object_storage

logger = structlog.get_logger()


RESOURCE_TYPES = {
    "pptx",
    "code_zip",
    "interactive_cards",
    "walkthrough",
    "narrated_video",
}

RESOURCE_STATUSES = {
    "not_generated",
    "generating",
    "ready",
    "failed",
}


class ResourceService:
    """Service for managing multimodal learning resources."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.storage: ObjectStorage = get_object_storage()

    async def get_or_create_resource(
        self,
        path_id: str,
        node_id: str,
        user_id: str,
        resource_type: str,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        """Get existing ready resource or start generation.

        Args:
            path_id: Learning path ID
            node_id: Learning node ID
            user_id: User ID
            resource_type: Type of resource (pptx, code_zip, interactive_cards, etc.)

        Returns:
            Dict with resource status, id, and optional task_id
        """
        if resource_type not in RESOURCE_TYPES:
            raise ApiError(
                code="INVALID_RESOURCE_TYPE",
                message=f"Invalid resource type: {resource_type}",
                status_code=400,
            )

        # Check for existing resource
        result = await self.db.execute(
            select(LearningResource).where(
                LearningResource.path_id == path_id,
                LearningResource.node_id == node_id,
                LearningResource.user_id == user_id,
                LearningResource.resource_type == resource_type,
            )
        )
        resource = result.scalar_one_or_none()

        # If ready, return existing unless an explicit regeneration was
        # requested. Regeneration is useful when source material or prompts
        # have been improved.
        if resource and resource.status == "ready" and not force:
            return {
                "resource_id": resource.id,
                "resource_type": resource_type,
                "status": "ready",
                "content": resource.content,
                "storage_key": resource.storage_key,
                "storage_provider": resource.storage_provider,
                "active_task_id": None,
            }

        # If generating, return task info
        if resource and resource.active_task_id:
            return {
                "resource_id": resource.id,
                "resource_type": resource_type,
                "status": "generating",
                "active_task_id": resource.active_task_id,
            }

        # Create new resource and enqueue generation task
        from app.services.task import TaskService

        task_service = TaskService(self.db)
        resource_id = resource.id if resource else str(uuid.uuid4())

        if not resource:
            resource = LearningResource(
                id=resource_id,
                user_id=user_id,
                path_id=path_id,
                node_id=node_id,
                resource_type=resource_type,
                status="generating",
            )
            self.db.add(resource)
            await self.db.flush()

        # Enqueue generation task
        retry_suffix = f":retry:{uuid.uuid4()}" if resource and (resource.status == "failed" or force) else ""
        idempotency_key = f"resource-generate:{user_id}:{node_id}:{resource_type}{retry_suffix}"
        task = await task_service.enqueue_task(
            user_id=user_id,
            task_type="interactive_resource_generation",
            target_type="node",
            target_id=node_id,
            target_metadata={
                "path_id": path_id,
                "resource_id": resource_id,
                "resource_type": resource_type,
            },
            idempotency_key=idempotency_key,
        )

        resource.active_task_id = task.id
        resource.status = "generating"
        resource.error_code = None
        resource.error_message = None
        await self.db.commit()

        return {
            "resource_id": resource_id,
            "resource_type": resource_type,
            "status": "generating",
            "active_task_id": task.id,
        }

    async def get_resource_content(
        self,
        path_id: str,
        node_id: str,
        user_id: str,
        resource_type: str,
    ) -> dict[str, Any]:
        """Get resource content (JSON for interactive, metadata for binary).

        For binary resources (PPTX, ZIP), returns metadata including storage key.
        For JSON resources (interactive cards), returns full content.
        """
        result = await self.db.execute(
            select(LearningResource).where(
                LearningResource.path_id == path_id,
                LearningResource.node_id == node_id,
                LearningResource.user_id == user_id,
                LearningResource.resource_type == resource_type,
            )
        )
        resource = result.scalar_one_or_none()

        if not resource:
            raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", status_code=404)

        if resource.status != "ready":
            return {
                "resource_id": resource.id,
                "resource_type": resource_type,
                "status": resource.status,
                "active_task_id": resource.active_task_id,
                "content": None,
            }

        # A database row can outlive its binary artifact (for example after a
        # local development restart using the old in-memory store). Mark it as
        # failed so the UI offers one-click regeneration instead of a broken
        # download button.
        if resource_type in ("pptx", "code_zip", "narrated_video") and (
            not resource.storage_key or not await self.storage.exists(resource.storage_key)
        ):
            resource.status = "failed"
            resource.active_task_id = None
            resource.error_code = "RESOURCE_ARTIFACT_NOT_FOUND"
            resource.error_message = "生成文件已丢失，请重新生成。"
            resource.updated_at = utc_now()
            await self.db.commit()
            return {
                "resource_id": resource.id,
                "resource_type": resource_type,
                "status": "failed",
                "active_task_id": None,
                "content": {
                    "error_code": resource.error_code,
                    "error_message": resource.error_message,
                },
            }

        # For binary resources, return storage info
        if resource_type in ("pptx", "code_zip", "narrated_video"):
            return {
                "resource_id": resource.id,
                "resource_type": resource_type,
                "status": "ready",
                "storage_key": resource.storage_key,
                "storage_provider": resource.storage_provider,
                "content": resource.content,  # Metadata (slide count, file list, etc.)
            }

        # For JSON resources (interactive), return full content
        return {
            "resource_id": resource.id,
            "resource_type": resource_type,
            "status": "ready",
            "content": resource.content,
        }

    async def get_unit_content_for_node(
        self,
        path_id: str,
        node_id: str,
        user_id: str,
    ) -> dict[str, Any] | None:
        """Get unit content for a node (used by resource generators)."""
        from sqlalchemy.orm import selectinload

        result = await self.db.execute(
            select(LearningUnitContent)
            .options(selectinload(LearningUnitContent.versions))
            .where(
                LearningUnitContent.path_id == path_id,
                LearningUnitContent.node_id == node_id,
                LearningUnitContent.user_id == user_id,
            )
        )
        content = result.scalar_one_or_none()

        if not content:
            return None

        # Get content data from active version or legacy
        if content.active_version_id and content.versions:
            active_version = next((v for v in content.versions if v.id == content.active_version_id), None)
            if active_version and active_version.content:
                return active_version.content

        return content.content or {}

    async def update_resource_ready(
        self,
        resource_id: str,
        content: dict[str, Any] | None = None,
        storage_key: str | None = None,
        storage_provider: str | None = None,
    ) -> None:
        """Mark resource as ready with content or storage info."""
        result = await self.db.execute(select(LearningResource).where(LearningResource.id == resource_id))
        resource = result.scalar_one_or_none()

        if resource:
            resource.status = "ready"
            resource.active_task_id = None
            resource.content = content
            resource.storage_key = storage_key
            resource.storage_provider = storage_provider
            resource.updated_at = utc_now()
            await self.db.commit()

    async def update_resource_failed(
        self,
        resource_id: str,
        error_code: str,
        error_message: str,
    ) -> None:
        """Mark resource as failed with error info."""
        result = await self.db.execute(select(LearningResource).where(LearningResource.id == resource_id))
        resource = result.scalar_one_or_none()

        if resource:
            resource.status = "failed"
            resource.active_task_id = None
            resource.error_code = error_code
            resource.error_message = error_message
            resource.updated_at = utc_now()
            await self.db.commit()

    async def download_resource_binary(
        self,
        path_id: str,
        node_id: str,
        user_id: str,
        resource_type: str,
    ) -> tuple[bytes, str, str]:
        """Download binary resource (PPTX/ZIP) after access validation.

        Returns:
            Tuple of (file_bytes, filename, content_type)

        Raises:
            ApiError: RESOURCE_NOT_FOUND, RESOURCE_NOT_READY, RESOURCE_NOT_BINARY
        """
        if resource_type not in ("pptx", "code_zip", "narrated_video"):
            raise ApiError(
                code="RESOURCE_NOT_BINARY",
                message=f"Resource type '{resource_type}' is not downloadable",
                status_code=400,
            )

        result = await self.db.execute(
            select(LearningResource).where(
                LearningResource.path_id == path_id,
                LearningResource.node_id == node_id,
                LearningResource.user_id == user_id,
                LearningResource.resource_type == resource_type,
            )
        )
        resource = result.scalar_one_or_none()

        if not resource:
            raise ApiError(code="RESOURCE_NOT_FOUND", message="Resource not found", status_code=404)

        if resource.status != "ready":
            raise ApiError(code="RESOURCE_NOT_READY", message="Resource is not ready", status_code=409)

        if not resource.storage_key:
            raise ApiError(
                code="RESOURCE_ARTIFACT_NOT_FOUND",
                message="Storage key not available for this resource",
                status_code=404,
            )

        try:
            file_bytes = await self.storage.get(resource.storage_key)
        except Exception as exc:
            raise ApiError(
                code="RESOURCE_ARTIFACT_NOT_FOUND",
                message="Artifact file not found in storage",
                status_code=404,
            ) from exc

        # Safe filename
        if resource_type == "pptx":
            filename = f"{node_id}-presentation.pptx"
            content_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        elif resource_type == "code_zip":
            filename = f"{node_id}-code-project.zip"
            content_type = "application/zip"
        else:
            filename = f"{node_id}-narrated-course.mp4"
            content_type = "video/mp4"

        return file_bytes, filename, content_type
