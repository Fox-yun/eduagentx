"""Unit content and assessment API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_deps import require_learning_user
from app.core.database import get_db
from app.models.user import User
from app.services.learning_access import require_node_access
from app.services.unit import UnitService

router = APIRouter()


class SubmitAssessmentRequest(BaseModel):
    answers: dict[str, str | list[str]]


class RegenerateContentRequest(BaseModel):
    preferences: str | None = None


@router.get("/{path_id}/nodes/{node_id}/content")
async def get_unit_content(
    path_id: str,
    node_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get unit content for a learning node."""
    await require_node_access(db, user.id, path_id, node_id)
    service = UnitService(db)
    return await service.get_unit_content(path_id, node_id, user.id)


@router.post("/{path_id}/nodes/{node_id}/content")
async def generate_unit_content(
    path_id: str,
    node_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Generate unit content for a learning node.

    Idempotent: returns existing content if already ready,
    or returns existing task_id if already generating.
    """
    await require_node_access(db, user.id, path_id, node_id)
    service = UnitService(db)
    return await service.generate_content(path_id, node_id, user.id)


@router.post("/{path_id}/nodes/{node_id}/content/regenerate")
async def regenerate_unit_content(
    path_id: str,
    node_id: str,
    body: RegenerateContentRequest = RegenerateContentRequest(),
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Regenerate unit content preserving existing active version.

    Safe regeneration: old content remains available via active_version
    until the worker atomically switches to the new version.
    """
    await require_node_access(db, user.id, path_id, node_id)
    service = UnitService(db)
    return await service.regenerate_content(path_id, node_id, user.id, body.preferences)


@router.post("/{path_id}/nodes/{node_id}/content/lecture")
async def generate_lecture(
    path_id: str,
    node_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Generate a detailed lecture for an existing unit content."""
    await require_node_access(db, user.id, path_id, node_id)

    from app.services.task import TaskService

    task_service = TaskService(db)
    task = await task_service.create_task(
        user_id=user.id,
        task_type="learning_lecture_generation",
        target_type="node",
        target_id=node_id,
        target_metadata={"path_id": path_id},
    )
    return {"next_step": "generating", "active_task_id": task.id}


@router.post("/{path_id}/nodes/{node_id}/assessments")
async def create_assessment(
    path_id: str,
    node_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create an assessment for a learning node."""
    await require_node_access(db, user.id, path_id, node_id)
    service = UnitService(db)
    return await service.create_assessment(path_id, node_id, user.id)


@router.post("/{path_id}/nodes/{node_id}/practice")
async def create_practice(
    path_id: str,
    node_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a practice question set (repeatable, not scored)."""
    await require_node_access(db, user.id, path_id, node_id)
    service = UnitService(db)
    return await service.create_practice(path_id, node_id, user.id)


async def submit_assessment(
    assessment_id: str,
    body: SubmitAssessmentRequest,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Submit an assessment attempt."""
    service = UnitService(db)
    return await service.submit_assessment(assessment_id, user.id, body.answers)
