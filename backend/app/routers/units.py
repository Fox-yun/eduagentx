"""Unit content and assessment API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_deps import require_learning_user
from app.core.database import get_db
from app.core.errors import ApiError
from app.models.progress import LearningProgress
from app.models.unit import Assessment, AssessmentAttempt, AssessmentQuestion
from app.models.user import User
from app.services.learning_access import require_node_access
from app.services.unit import UnitService, _safe_question_dto

router = APIRouter()


class SubmitAssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: dict[str, str | list[str] | bool]
    client_request_id: str | None = None


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
    purpose: str = "formal",
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create an assessment for a learning node.

    Uses async background generation via learning_assessment_generation worker.
    Returns generating status and active_task_id for SSE progress tracking.
    Idempotent: returns existing if ready, or existing task_id if generating.

    Purpose defaults to 'formal' (scored, updates mastery). Use
    `purpose=quiz_bank` for practice question sets.
    """
    await require_node_access(db, user.id, path_id, node_id)
    service = UnitService(db)
    return await service.create_assessment(path_id, node_id, user.id, purpose=purpose)


@router.get("/{path_id}/nodes/{node_id}/assessments/{assessment_id}")
async def get_assessment(
    path_id: str,
    node_id: str,
    assessment_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get assessment status and questions (if ready).

    Returns the current state of an assessment. When status is "ready",
    includes the full question list (without answers). Use this endpoint
    to poll for async generation completion.
    """
    await require_node_access(db, user.id, path_id, node_id)

    # Resolve active version for validation
    from app.models.path import LearningPath

    path_result = await db.execute(select(LearningPath).where(LearningPath.id == path_id))
    path = path_result.scalar_one_or_none()
    active_version_id = path.active_version_id if path else None

    result = await db.execute(
        select(Assessment).where(
            Assessment.id == assessment_id,
            Assessment.user_id == user.id,
            Assessment.path_id == path_id,
            Assessment.node_id == node_id,
            Assessment.path_version_id == active_version_id,
        )
    )
    assessment = result.scalar_one_or_none()
    if not assessment:
        raise ApiError(code="ASSESSMENT_NOT_FOUND", message="Assessment not found", status_code=404)

    if assessment.status == "ready":
        q_result = await db.execute(
            select(AssessmentQuestion)
            .where(AssessmentQuestion.assessment_id == assessment.id)
            .order_by(AssessmentQuestion.question_order)
        )
        questions = [_safe_question_dto(q) for q in q_result.scalars().all()]
        return {
            "assessment_id": assessment.id,
            "purpose": assessment.purpose,
            "status": "ready",
            "active_task_id": None,
            "questions": questions,
        }

    return {
        "assessment_id": assessment.id,
        "purpose": assessment.purpose,
        "status": assessment.status,
        "active_task_id": assessment.active_task_id,
        "questions": [],
    }


@router.post("/{path_id}/nodes/{node_id}/practice")
async def create_practice(
    path_id: str,
    node_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a practice question set (repeatable, not scored).

    Delegates to the async assessment generation pipeline with
    purpose=practice, ensuring consistent architecture with formal
    assessments and quiz banks.
    """
    await require_node_access(db, user.id, path_id, node_id)
    service = UnitService(db)
    return await service.create_assessment(path_id, node_id, user.id, purpose="practice")


@router.get("/{path_id}/nodes/{node_id}/mind-map")
async def get_mind_map(
    path_id: str,
    node_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get a mind map tree generated from unit content (deterministic, no LLM)."""
    await require_node_access(db, user.id, path_id, node_id)
    service = UnitService(db)
    return await service.get_mind_map(path_id, node_id, user.id)


@router.post("/{path_id}/nodes/{node_id}/quiz-bank")
async def generate_quiz_bank(
    path_id: str,
    node_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Generate a quiz bank for a learning node (async background task).

    Uses transactional outbox for reliability. Idempotent:
    returns existing if already ready, or existing task if generating.
    """
    await require_node_access(db, user.id, path_id, node_id)
    service = UnitService(db)
    return await service.generate_quiz_bank(path_id, node_id, user.id)


@router.get("/{path_id}/nodes/{node_id}/quiz-bank")
async def get_quiz_bank(
    path_id: str,
    node_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get existing quiz bank for a node, if ready."""
    await require_node_access(db, user.id, path_id, node_id)

    # Resolve active version for filtering
    from app.models.path import LearningPath

    path_result = await db.execute(select(LearningPath).where(LearningPath.id == path_id))
    path = path_result.scalar_one_or_none()
    active_version_id = path.active_version_id if path else None

    result = await db.execute(
        select(Assessment).where(
            Assessment.path_id == path_id,
            Assessment.node_id == node_id,
            Assessment.user_id == user.id,
            Assessment.purpose == "quiz_bank",
            Assessment.path_version_id == active_version_id,
        )
    )
    assessment = result.scalar_one_or_none()
    if not assessment:
        return {"assessment_id": None, "status": "not_generated", "questions": []}

    if assessment.status == "ready":
        q_result = await db.execute(
            select(AssessmentQuestion)
            .where(AssessmentQuestion.assessment_id == assessment.id)
            .order_by(AssessmentQuestion.question_order)
        )
        return {
            "assessment_id": assessment.id,
            "status": "ready",
            "questions": [_safe_question_dto(q) for q in q_result.scalars().all()],
        }

    return {
        "assessment_id": assessment.id,
        "status": assessment.status,
        "active_task_id": assessment.active_task_id,
        "questions": [],
    }


async def submit_assessment(
    assessment_id: str,
    body: SubmitAssessmentRequest,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Submit an assessment attempt."""
    service = UnitService(db)
    return await service.submit_assessment(
        assessment_id, user.id, body.answers, client_request_id=body.client_request_id
    )


@router.get("/{path_id}/nodes/{node_id}/attempts/{attempt_id}")
async def get_attempt_result(
    path_id: str,
    node_id: str,
    attempt_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get the result of a completed assessment attempt.

    Validates that the attempt belongs to an assessment for the given
    path_id and node_id, preventing cross-path access.
    """
    result = await db.execute(
        select(AssessmentAttempt).where(
            AssessmentAttempt.id == attempt_id,
            AssessmentAttempt.user_id == user.id,
        )
    )
    attempt = result.scalar_one_or_none()
    if not attempt:
        raise ApiError(code="ATTEMPT_NOT_FOUND", message="Attempt not found", status_code=404)

    # Validate attempt belongs to assessment for this path/node
    assess_result = await db.execute(
        select(Assessment).where(
            Assessment.id == attempt.assessment_id,
        )
    )
    assessment = assess_result.scalar_one_or_none()
    if not assessment or assessment.path_id != path_id or assessment.node_id != node_id:
        raise ApiError(
            code="ATTEMPT_PATH_MISMATCH",
            message="Attempt does not belong to the specified path/node",
            status_code=404,
        )

    prog = await db.execute(
        select(LearningProgress).where(
            LearningProgress.user_id == user.id,
            LearningProgress.node_id == node_id,
        )
    )
    progress = prog.scalar_one_or_none()

    return {
        "attempt_id": attempt.id,
        "status": attempt.status,
        "grading_quality": attempt.grading_quality,
        "score": attempt.score,
        "assessment_passed": getattr(attempt, "assessment_passed", None),
        "mastery_before": attempt.mastery_before,
        "mastery_after": attempt.mastery_after,
        "node_completed": getattr(attempt, "node_completed", None),
        "mastery_updated": attempt.progress_applied_at is not None,
        "progress_status": progress.status if progress else None,
        "unlocked_node_ids": attempt.unlocked_node_ids or [],
    }
