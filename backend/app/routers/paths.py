"""Learning path API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_deps import require_learning_user
from app.core.database import get_db
from app.models.user import User
from app.services.path import PathService

router = APIRouter()


class RevisionRequest(BaseModel):
    revision_request: str


@router.get("/")
async def list_paths(
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List all learning paths for the current user."""
    service = PathService(db)
    items = await service.list_user_paths(user.id)
    return {"items": items, "total": len(items)}


@router.delete("/{path_id}")
async def delete_path(
    path_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Delete (archive) a learning path."""
    service = PathService(db)
    await service.delete_path(path_id, user.id)
    return {"status": "deleted"}


@router.get("/{path_id}")
async def get_path(
    path_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get a learning path with all details."""
    service = PathService(db)
    return await service.get_path_with_details(path_id, user.id)


@router.get("/{path_id}/versions")
async def list_versions(
    path_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List all versions of a learning path."""
    service = PathService(db)
    versions = await service.list_versions(path_id, user.id)

    # Map internal status to frontend enum
    status_map = {
        "draft": "draft",
        "in_review": "draft",
        "active": "active",
        "superseded": "archived",
        "rejected": "archived",
        "failed": "failed",
    }

    return {
        "items": [
            {
                "path_id": v.path_id,
                "version": v.version_number,
                "parent_version": None,
                "status": status_map.get(v.status, "draft"),
                "revision_reason": None,
                "generation_summary": v.summary,
                "total_estimated_minutes": v.estimated_total_minutes,
                "critic_score": None,
                "created_at": str(v.created_at),
                "activated_at": str(v.activated_at) if v.activated_at else None,
            }
            for v in versions
        ],
        "next_cursor": None,
        "total": len(versions),
    }


@router.get("/{path_id}/versions/{version_id}")
async def get_version(
    path_id: str,
    version_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get a specific version's full details."""
    service = PathService(db)
    return await service.get_version_with_details(path_id, user.id, version_id)


@router.get("/{path_id}/versions/{version_id}/diff")
async def get_version_diff(
    path_id: str,
    version_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Compute diff between active version and the specified version."""
    service = PathService(db)
    return await service.compute_version_diff(path_id, user.id, version_id)


@router.post("/{path_id}/versions/{version_id}/activate")
async def activate_version(
    path_id: str,
    version_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Activate a specific version of a learning path.

    The version must be in_review status.
    Old active version is superseded atomically.
    Learning progress is migrated by logical_key.
    """
    service = PathService(db)
    path = await service.activate_version(path_id, user.id, version_id)
    return {"message": "Version activated", "path_id": path.id, "version_id": version_id}


@router.post("/{path_id}/revision-requests")
async def create_revision_request(
    path_id: str,
    body: RevisionRequest,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a revision request for a path.

    Atomically creates the revision request and a background task.
    Returns a real active_task_id so the frontend can poll progress.
    """
    service = PathService(db)
    revision_req, task = await service.create_revision_request(path_id, user.id, body.revision_request)

    await db.commit()

    return {
        "next_step": "generating",
        "active_task_id": task.id if task else None,
        "revision_request_id": revision_req.id,
    }


@router.get("/{path_id}/recommendations")
async def get_recommendations(
    path_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get rule-based learning recommendations for a path.

    Generates recommendations based on:
      - Review: nodes with mastery < 60% or failed assessments
      - Practice: available nodes not yet completed
      - Continue: earliest available node
      - Resource: knowledge base search hits matching node titles
    """
    from app.services.recommendations import RecommendationService

    service = RecommendationService(db)
    items = await service.get_recommendations(path_id, user.id)
    return {"items": items}
