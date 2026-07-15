"""Learning path API endpoints."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_deps import require_learning_user
from app.core.database import get_db
from app.models.path import LearningPath
from app.models.progress import RecommendationFeedback
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
                "version_id": v.id,
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


@router.post("/{path_id}/activate")
async def activate_path(
    path_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Activate the newest draft/review version of a learning path."""
    service = PathService(db)
    path, version_id = await service.activate_latest_version(path_id, user.id)
    return {"message": "Path activated", "path_id": path.id, "version_id": version_id}


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
    """Get dynamic learning recommendations for a path.

    Generates recommendations based on:
      - Review: nodes with mastery < 60% or failed assessments
      - Review Weak Point: error_pattern from profile triggers targeted review
      - Practice: available nodes not yet completed
      - Continue: earliest available node
      - Ask Tutor: low concept_grasp suggests asking the tutor
      - Resource: knowledge base search hits matching node titles
      - Revise Path: consecutive assessment failures suggest path revision

    Each recommendation includes evidence, priority, confidence, and action.
    """
    from app.services.recommendations import RecommendationService

    service = RecommendationService(db)
    items = await service.get_recommendations(path_id, user.id)
    return {"items": items}


class RecommendationFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendation_key: str = Field(min_length=1, max_length=100)
    recommendation_type: str = Field(min_length=1, max_length=30)
    node_id: str | None = None
    action: Literal["accept", "ignore", "later"]


class AdaptationDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["accept", "dismiss"]


@router.get("/{path_id}/adaptation-proposals")
async def get_adaptation_proposals(
    path_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    from app.services.adaptation import list_adaptation_proposals, serialize_adaptation_proposal

    items = await list_adaptation_proposals(db, user_id=user.id, path_id=path_id)
    return {"items": [serialize_adaptation_proposal(item) for item in items]}


@router.post("/{path_id}/adaptation-proposals/{proposal_id}/decision")
async def decide_adaptation(
    path_id: str,
    proposal_id: str,
    body: AdaptationDecisionRequest,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    from app.services.adaptation import decide_adaptation_proposal, serialize_adaptation_proposal

    proposal, task_id = await decide_adaptation_proposal(
        db,
        user_id=user.id,
        path_id=path_id,
        proposal_id=proposal_id,
        action=body.action,
    )
    await db.commit()
    return {"proposal": serialize_adaptation_proposal(proposal), "active_task_id": task_id}


@router.post("/{path_id}/recommendations/feedback")
async def submit_recommendation_feedback(
    path_id: str,
    body: RecommendationFeedbackRequest,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Submit user feedback on a recommendation (accept / ignore / later).

    The feedback is persisted to track user preferences and improve
    future recommendation ordering. The recommendation_key uniquely
    identifies a recommendation type+node combination for deduplication.
    """
    owned_path = await db.execute(
        select(LearningPath.id).where(LearningPath.id == path_id, LearningPath.user_id == user.id)
    )
    if owned_path.scalar_one_or_none() is None:
        from app.core.errors import ApiError

        raise ApiError(code="PATH_NOT_FOUND", message="Learning path not found", status_code=404)

    # Check if feedback already exists (idempotent update)
    existing = await db.execute(
        select(RecommendationFeedback).where(
            RecommendationFeedback.user_id == user.id,
            RecommendationFeedback.recommendation_key == body.recommendation_key,
        )
    )
    existing_feedback = existing.scalar_one_or_none()

    if existing_feedback:
        # Update existing feedback
        existing_feedback.action = body.action
    else:
        # Create new feedback
        feedback = RecommendationFeedback(
            user_id=user.id,
            path_id=path_id,
            recommendation_key=body.recommendation_key,
            recommendation_type=body.recommendation_type,
            node_id=body.node_id,
            action=body.action,
        )
        db.add(feedback)

    await db.commit()
    return {"status": "ok", "action": body.action}
