"""Unit content and assessment API endpoints."""

from __future__ import annotations

import io
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response, StreamingResponse
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
from app.services.resources import ResourceService
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
    service = UnitService(db)
    return await service.generate_lecture(path_id, node_id, user.id)


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
    """Create a repeatable, unscored practice set with answer feedback."""
    await require_node_access(db, user.id, path_id, node_id)
    service = UnitService(db)
    return await service.create_practice(path_id, node_id, user.id)


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


@router.get("/{path_id}/nodes/{node_id}/interactive-cards")
async def get_interactive_cards(
    path_id: str,
    node_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get interactive learning cards generated from unit content (deterministic, no LLM).

    Returns flip cards with front (question) and back (answer),
    covering concepts, key terms, and practice tasks.
    """
    await require_node_access(db, user.id, path_id, node_id)
    service = UnitService(db)
    return await service.get_interactive_cards(path_id, node_id, user.id)


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


# ---------------------------------------------------------------------------#
# Multimodal Resources API (Phase 3.9)
# ---------------------------------------------------------------------------#


@router.post("/{path_id}/nodes/{node_id}/resources/{resource_type}")
async def generate_resource(
    path_id: str,
    node_id: str,
    resource_type: str,
    force: bool = False,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Generate a multimodal learning resource.

    Supported resource types:
    - pptx: PowerPoint presentation
    - code_zip: Code project ZIP archive
    - interactive_cards: Flip card learning resources
    - walkthrough: Step-by-step case study
    - narrated_video: Narrated MP4 lesson with synchronized captions

    Returns generating status with active_task_id for SSE progress tracking.
    Idempotent: returns existing resource if ready, or existing task_id if generating.
    """
    await require_node_access(db, user.id, path_id, node_id)
    service = ResourceService(db)
    return await service.get_or_create_resource(path_id, node_id, user.id, resource_type, force=force)


@router.get("/{path_id}/nodes/{node_id}/resources/{resource_type}")
async def get_resource(
    path_id: str,
    node_id: str,
    resource_type: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get a multimodal learning resource.

    For binary resources (PPTX, ZIP), returns metadata including storage key.
    For JSON resources (interactive cards and walkthrough), returns full content.
    """
    await require_node_access(db, user.id, path_id, node_id)
    service = ResourceService(db)
    return await service.get_resource_content(path_id, node_id, user.id, resource_type)


@router.get("/{path_id}/nodes/{node_id}/resources/{resource_type}/download")
async def download_resource(
    path_id: str,
    node_id: str,
    resource_type: str,
    request: Request,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Download a binary learning resource, including seekable MP4 ranges.

    Validates user access and resource readiness before streaming the
    binary artifact from object storage.  The storage key is never exposed
    to the client — only a safe filename is returned in the
    Content-Disposition header.

    Supported resource types: ``pptx``, ``code_zip``, ``narrated_video``.
    """
    await require_node_access(db, user.id, path_id, node_id)
    service = ResourceService(db)
    file_bytes, filename, content_type = await service.download_resource_binary(
        path_id, node_id, user.id, resource_type
    )
    total_size = len(file_bytes)
    disposition = "inline" if resource_type == "narrated_video" else "attachment"
    headers = {
        "Content-Disposition": f'{disposition}; filename="{filename}"',
        "Content-Length": str(total_size),
    }

    if resource_type == "narrated_video":
        headers["Accept-Ranges"] = "bytes"
        range_header = request.headers.get("range")
        if range_header:
            try:
                start, end = _parse_byte_range(range_header, total_size)
            except ValueError:
                return Response(
                    status_code=416,
                    headers={"Content-Range": f"bytes */{total_size}", "Accept-Ranges": "bytes"},
                )
            partial = file_bytes[start : end + 1]
            headers.update(
                {
                    "Content-Range": f"bytes {start}-{end}/{total_size}",
                    "Content-Length": str(len(partial)),
                }
            )
            return Response(content=partial, status_code=206, media_type=content_type, headers=headers)

    return StreamingResponse(
        io.BytesIO(file_bytes),
        media_type=content_type,
        headers=headers,
    )


def _parse_byte_range(value: str, total_size: int) -> tuple[int, int]:
    """Parse one RFC 7233 byte range and clamp its end to the file size."""
    if total_size <= 0 or not value.startswith("bytes=") or "," in value:
        raise ValueError("Unsupported byte range")
    spec = value.removeprefix("bytes=").strip()
    if "-" not in spec:
        raise ValueError("Malformed byte range")
    start_text, end_text = (part.strip() for part in spec.split("-", 1))
    try:
        if not start_text:
            suffix_length = int(end_text)
            if suffix_length <= 0:
                raise ValueError("Invalid suffix range")
            start = max(total_size - suffix_length, 0)
            end = total_size - 1
        else:
            start = int(start_text)
            end = int(end_text) if end_text else total_size - 1
            if start < 0 or start >= total_size or end < start:
                raise ValueError("Unsatisfiable byte range")
            end = min(end, total_size - 1)
    except (TypeError, ValueError) as exc:
        raise ValueError("Malformed byte range") from exc
    return start, end
