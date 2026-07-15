"""Learner-confirmed learning-path adaptation proposals."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.models.path import LearningPath
from app.models.progress import LearningPathAdaptationProposal
from app.models.unit import Assessment, AssessmentAttempt

CONSECUTIVE_FAILURE_THRESHOLD = 2


async def ensure_failure_adaptation_proposal(
    db: AsyncSession,
    *,
    user_id: str,
    path_id: str,
    trigger_node_id: str,
) -> LearningPathAdaptationProposal | None:
    """Create one open proposal when the latest formal attempts are failures."""
    rows = (
        await db.execute(
            select(AssessmentAttempt, Assessment)
            .join(Assessment, Assessment.id == AssessmentAttempt.assessment_id)
            .where(
                AssessmentAttempt.user_id == user_id,
                Assessment.path_id == path_id,
                AssessmentAttempt.status == "completed",
                AssessmentAttempt.finalized_at.is_not(None),
            )
            .order_by(AssessmentAttempt.finalized_at.desc())
            .limit(CONSECUTIVE_FAILURE_THRESHOLD)
        )
    ).all()
    if len(rows) < CONSECUTIVE_FAILURE_THRESHOLD or any(bool(attempt.assessment_passed) for attempt, _ in rows):
        return None

    existing = (
        await db.execute(
            select(LearningPathAdaptationProposal).where(
                LearningPathAdaptationProposal.user_id == user_id,
                LearningPathAdaptationProposal.path_id == path_id,
                LearningPathAdaptationProposal.status == "proposed",
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    attempts = [attempt for attempt, _ in rows]
    assessments = [assessment for _, assessment in rows]
    node_ids = list(dict.fromkeys(assessment.node_id for assessment in assessments))
    proposal = LearningPathAdaptationProposal(
        user_id=user_id,
        path_id=path_id,
        trigger_node_id=trigger_node_id,
        status="proposed",
        reason=f"最近 {CONSECUTIVE_FAILURE_THRESHOLD} 次正式评估均未通过，建议先补齐基础并降低下一阶段跨度。",
        evidence={
            "trigger": "consecutive_assessment_failures",
            "attempt_ids": [attempt.id for attempt in attempts],
            "node_ids": node_ids,
            "scores": [float(attempt.score or 0) for attempt in attempts],
        },
        proposed_changes=[
            {"type": "add_remedial_node", "label": "在薄弱节点前增加基础补强单元"},
            {"type": "increase_practice", "label": "增加针对易错点的练习与代码实操"},
            {"type": "adjust_pace", "label": "降低后续知识跨度并预留复习时间"},
        ],
    )
    db.add(proposal)
    await db.flush()
    return proposal


async def list_adaptation_proposals(
    db: AsyncSession, *, user_id: str, path_id: str
) -> list[LearningPathAdaptationProposal]:
    await _require_owned_path(db, user_id=user_id, path_id=path_id)
    result = await db.execute(
        select(LearningPathAdaptationProposal)
        .where(
            LearningPathAdaptationProposal.user_id == user_id,
            LearningPathAdaptationProposal.path_id == path_id,
        )
        .order_by(LearningPathAdaptationProposal.created_at.desc())
    )
    return list(result.scalars().all())


async def decide_adaptation_proposal(
    db: AsyncSession,
    *,
    user_id: str,
    path_id: str,
    proposal_id: str,
    action: str,
) -> tuple[LearningPathAdaptationProposal, str | None]:
    proposal = (
        await db.execute(
            select(LearningPathAdaptationProposal)
            .where(
                LearningPathAdaptationProposal.id == proposal_id,
                LearningPathAdaptationProposal.user_id == user_id,
                LearningPathAdaptationProposal.path_id == path_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if proposal is None:
        raise ApiError(code="ADAPTATION_NOT_FOUND", message="Adaptation proposal not found", status_code=404)
    if proposal.status != "proposed":
        return proposal, None

    proposal.decided_at = datetime.now(UTC)
    if action == "dismiss":
        proposal.status = "dismissed"
        await db.flush()
        return proposal, None

    from app.services.path import PathService

    change_text = "；".join(str(item.get("label", "")) for item in proposal.proposed_changes)
    revision, task = await PathService(db).create_revision_request(
        path_id,
        user_id,
        f"根据学习效果适配提案调整路径：{change_text}。触发原因：{proposal.reason}",
    )
    proposal.status = "accepted"
    proposal.revision_request_id = revision.id
    await db.flush()
    return proposal, task.id if task else None


def serialize_adaptation_proposal(proposal: LearningPathAdaptationProposal) -> dict[str, Any]:
    return {
        "id": proposal.id,
        "path_id": proposal.path_id,
        "trigger_node_id": proposal.trigger_node_id,
        "status": proposal.status,
        "reason": proposal.reason,
        "evidence": proposal.evidence,
        "proposed_changes": proposal.proposed_changes,
        "revision_request_id": proposal.revision_request_id,
        "created_at": proposal.created_at.isoformat() if proposal.created_at else None,
        "decided_at": proposal.decided_at.isoformat() if proposal.decided_at else None,
    }


async def _require_owned_path(db: AsyncSession, *, user_id: str, path_id: str) -> LearningPath:
    path = (
        await db.execute(select(LearningPath).where(LearningPath.id == path_id, LearningPath.user_id == user_id))
    ).scalar_one_or_none()
    if path is None:
        raise ApiError(code="PATH_NOT_FOUND", message="Learning path not found", status_code=404)
    return path
