"""Worker handlers for multimodal resource generation.

Handles PPTX, Code ZIP, and Interactive resource generation tasks.
"""

from __future__ import annotations

import structlog
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import BackgroundTask
from app.models.unit import LearningResource
from app.services.code_generator import CodeZIPGenerator
from app.services.interactive_generator import InteractiveGenerator
from app.services.pptx_generator import PPTXGenerator
from app.services.resources import ResourceService
from app.services.storage import get_object_storage

logger = structlog.get_logger()


async def execute_resource_generation(
    db: AsyncSession,
    task: BackgroundTask,
) -> dict[str, Any]:
    """Execute multimodal resource generation.

    Supported resource types:
    - pptx: PowerPoint presentation (deterministic from unit content)
    - code_zip: Code project ZIP archive (with security checks)
    - interactive_cards: Flip card learning resources (already in unit.py)
    - walkthrough: Step-by-step case study
    - simulation: Concept simulation with state transitions

    Args:
        db: Database session
        task: Background task with metadata:
            - path_id: Learning path ID
            - resource_id: Learning resource ID
            - resource_type: Type of resource to generate

    Returns:
        Dict with generation result
    """
    metadata = task.target_metadata or {}
    path_id = metadata.get("path_id")
    resource_id = metadata.get("resource_id")
    resource_type = metadata.get("resource_type")
    user_id = task.user_id

    if not all([path_id, resource_id, resource_type, user_id]):
        raise ValueError("Missing required metadata: path_id, resource_id, resource_id, resource_type")

    resource_service = ResourceService(db)
    storage = get_object_storage()

    # Get node_id from resource
    result = await db.execute(select(LearningResource).where(LearningResource.id == resource_id))
    resource = result.scalar_one_or_none()
    if not resource:
        raise ValueError(f"Resource not found: {resource_id}")
    node_id = resource.node_id

    # Get unit content for generation
    unit_content = await resource_service.get_unit_content_for_node(path_id, node_id, user_id)
    if not unit_content:
        error_msg = f"Unit content not found for node {node_id}"
        await resource_service.update_resource_failed(
            resource_id, "UNIT_CONTENT_NOT_FOUND", error_msg
        )
        raise ValueError(error_msg)

    try:
        # Route to appropriate generator based on resource_type
        if resource_type == "pptx":
            result_data = await _generate_pptx(
                resource_id, node_id, user_id, unit_content, storage, resource_service
            )
        elif resource_type == "code_zip":
            result_data = await _generate_code_zip(
                resource_id, node_id, user_id, unit_content, storage, resource_service
            )
        elif resource_type == "interactive_cards":
            result_data = await _generate_interactive_cards(
                resource_id, node_id, user_id, unit_content, resource_service
            )
        elif resource_type == "walkthrough":
            result_data = await _generate_walkthrough(
                resource_id, node_id, user_id, unit_content, resource_service
            )
        elif resource_type == "simulation":
            result_data = await _generate_simulation(
                resource_id, node_id, user_id, unit_content, resource_service
            )
        else:
            error_msg = f"Unsupported resource type: {resource_type}"
            await resource_service.update_resource_failed(resource_id, "UNSUPPORTED_TYPE", error_msg)
            raise ValueError(error_msg)

        logger.info(
            "resource_generation_completed",
            resource_id=resource_id,
            resource_type=resource_type,
            node_id=node_id,
        )
        return result_data

    except Exception as e:
        error_msg = f"Resource generation failed: {str(e)}"
        logger.error(
            "resource_generation_failed",
            resource_id=resource_id,
            resource_type=resource_type,
            error=str(e),
        )
        await resource_service.update_resource_failed(resource_id, "GENERATION_ERROR", error_msg)
        raise


async def _generate_pptx(
    resource_id: str,
    node_id: str,
    user_id: str,
    unit_content: dict[str, Any],
    storage,
    resource_service: ResourceService,
) -> dict[str, Any]:
    """Generate PPTX and upload to storage."""
    pptx_bytes = PPTXGenerator.generate_pptx_bytes(unit_content)
    if not pptx_bytes:
        raise RuntimeError("PPTX generation returned empty bytes")

    # Upload to storage
    storage_key = f"resources/{user_id}/{node_id}/presentation.pptx"
    await storage.put(storage_key, pptx_bytes, content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")

    # Count slides
    try:
        from pptx import Presentation
        from io import BytesIO

        prs = Presentation(BytesIO(pptx_bytes))
        slide_count = len(prs.slides)
    except Exception:
        slide_count = 0

    from app.common.datetime import utc_now

    content_metadata = {
        "slide_count": slide_count,
        "title": unit_content.get("introduction", "").split("\n")[0][:100],
        "generated_at": utc_now().isoformat(),
    }

    await resource_service.update_resource_ready(
        resource_id,
        content=content_metadata,
        storage_key=storage_key,
        storage_provider="minio",
    )

    return {
        "resource_id": resource_id,
        "storage_key": storage_key,
        "slide_count": slide_count,
    }


async def _generate_code_zip(
    resource_id: str,
    node_id: str,
    user_id: str,
    unit_content: dict[str, Any],
    storage,
    resource_service: ResourceService,
) -> dict[str, Any]:
    """Generate code ZIP and upload to storage."""
    zip_bytes, file_list = CodeZIPGenerator.generate_zip_bytes(unit_content)
    if not zip_bytes:
        raise RuntimeError("Code ZIP generation returned empty bytes")

    # Upload to storage
    storage_key = f"resources/{user_id}/{node_id}/code-project.zip"
    await storage.put(storage_key, zip_bytes, content_type="application/zip")

    content_metadata = {
        "file_count": len(file_list),
        "files": file_list,
        "title": unit_content.get("introduction", "").split("\n")[0][:100],
    }

    await resource_service.update_resource_ready(
        resource_id,
        content=content_metadata,
        storage_key=storage_key,
        storage_provider="minio",
    )

    return {
        "resource_id": resource_id,
        "storage_key": storage_key,
        "file_count": len(file_list),
    }


async def _generate_interactive_cards(
    resource_id: str,
    node_id: str,
    user_id: str,
    unit_content: dict[str, Any],
    resource_service: ResourceService,
) -> dict[str, Any]:
    """Generate interactive cards (stored as JSON, no file upload)."""
    cards_data = InteractiveGenerator.generate_cards(unit_content)

    content_metadata = {
        "title": cards_data["title"],
        "interactive_type": "cards",
        "description": cards_data["description"],
        "items": cards_data["items"],
        "knowledge_points": cards_data["knowledge_points"],
        "estimated_minutes": cards_data["estimated_minutes"],
        "card_count": len(cards_data["items"]),
    }

    await resource_service.update_resource_ready(resource_id, content=content_metadata)

    return {
        "resource_id": resource_id,
        "card_count": len(cards_data["items"]),
    }


async def _generate_walkthrough(
    resource_id: str,
    node_id: str,
    user_id: str,
    unit_content: dict[str, Any],
    resource_service: ResourceService,
) -> dict[str, Any]:
    """Generate walkthrough (step-by-step case study)."""
    walkthrough_data = InteractiveGenerator.generate_walkthrough(unit_content)

    content_metadata = {
        "title": walkthrough_data["title"],
        "interactive_type": "walkthrough",
        "description": walkthrough_data["description"],
        "items": walkthrough_data["items"],
        "step_count": len(walkthrough_data["items"]),
    }

    await resource_service.update_resource_ready(resource_id, content=content_metadata)

    return {
        "resource_id": resource_id,
        "step_count": len(walkthrough_data["items"]),
    }


async def _generate_simulation(
    resource_id: str,
    node_id: str,
    user_id: str,
    unit_content: dict[str, Any],
    resource_service: ResourceService,
) -> dict[str, Any]:
    """Generate simulation (concept state transitions)."""
    simulation_data = InteractiveGenerator.generate_simulation(unit_content)

    content_metadata = {
        "title": simulation_data["title"],
        "interactive_type": "simulation",
        "description": simulation_data["description"],
        "items": simulation_data["items"],
        "state_count": len(simulation_data["items"]),
    }

    await resource_service.update_resource_ready(resource_id, content=content_metadata)

    return {
        "resource_id": resource_id,
        "state_count": len(simulation_data["items"]),
    }