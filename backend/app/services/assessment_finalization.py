"""Unified assessment finalization service.

Phase 3.5-C1: Correctness closure — all P0 issues resolved.

Rules:
  - assessment_passed (>=60) and node_completed (>=70) are independent
  - Only formal assessments may update mastery/progress/unlock
  - Provisional grading NEVER updates progress
  - Monotonic completion: once a node is completed it is never auto-downgraded
  - DAG unlock uses all-prerequisites-met strategy
  - Path-level FOR UPDATE serialises concurrent finalization on the same path
  - Profile evidence is idempotent (PostgreSQL ON CONFLICT DO NOTHING)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import structlog
from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.models.path import LearningEdge, LearningPath
from app.models.progress import LearningProgress, MasterySnapshot
from app.models.unit import Assessment, AssessmentAnswer, AssessmentAttempt
from app.models.user import StudentProfileEvidence

logger = structlog.get_logger()

# Assessment pass threshold — a score >= 60 means the assessment is passed
ASSESSMENT_PASS_THRESHOLD = Decimal("60.00")

# Node mastery pass threshold — independent of assessment pass threshold
NODE_MASTERY_PASS_THRESHOLD = Decimal("70.00")

# Weight for existing mastery when re-assessing
MASTERY_HISTORY_WEIGHT = Decimal("0.30")
MASTERY_ASSESSMENT_WEIGHT = Decimal("0.70")

# Evidence dimensions recorded per formal attempt
EVIDENCE_DIMENSIONS: tuple[dict[str, Any], ...] = (
    {"dimension": "concept_grasp", "confidence": 0.84},
    {"dimension": "knowledge_depth", "confidence": 0.78},
)


@dataclass(frozen=True)
class AssessmentFinalizationResult:
    """Result of finalizing an assessment attempt."""

    attempt_id: str
    grading_quality: str
    percentage: Decimal
    assessment_passed: bool
    node_completed: bool
    mastery_before: Decimal
    mastery_after: Decimal
    mastery_updated: bool
    unlocked_node_ids: tuple[str, ...] = field(default_factory=tuple)
    profile_evidence_ids: tuple[str, ...] = field(default_factory=tuple)


async def finalize_assessment_attempt(
    db: AsyncSession,
    *,
    attempt_id: str,
) -> AssessmentFinalizationResult:
    """Finalize a completed assessment attempt.

    Single entry point for all mastery/progress/unlock/evidence updates.
    Must be called within an active transaction (caller commits).

    Concurrency: FOR UPDATE on Attempt then Path serialises all
    finalization for the same learning path, preventing lost mastery
    updates and concurrent-unlock races.
    """
    # ------------------------------------------------------------------
    # 1. Lock attempt and verify it exists
    # ------------------------------------------------------------------
    attempt = (
        await db.execute(select(AssessmentAttempt).where(AssessmentAttempt.id == attempt_id).with_for_update())
    ).scalar_one_or_none()
    if not attempt:
        raise ApiError(code="ATTEMPT_NOT_FOUND", message="Assessment attempt not found", status_code=404)

    # 2. Re-entry guard — result already solidified
    if attempt.finalized_at is not None:
        return _build_reentry_result(attempt)

    # 3. Must be completed
    if attempt.status != "completed":
        raise ApiError(
            code="ATTEMPT_NOT_COMPLETED",
            message=f"Cannot finalize attempt with status '{attempt.status}'",
            status_code=409,
        )

    # ------------------------------------------------------------------
    # 4. Load assessment
    # ------------------------------------------------------------------
    assessment = (
        await db.execute(select(Assessment).where(Assessment.id == attempt.assessment_id))
    ).scalar_one_or_none()
    if not assessment:
        raise ApiError(code="ASSESSMENT_NOT_FOUND", message="Assessment not found", status_code=404)

    # ------------------------------------------------------------------
    # 5. Aggregate scores (pure Decimal arithmetic)
    # ------------------------------------------------------------------
    agg = await db.execute(
        select(
            sa_func.coalesce(sa_func.sum(AssessmentAnswer.points_earned), 0).label("earned"),
            sa_func.coalesce(sa_func.sum(AssessmentAnswer.max_score), 0).label("max_possible"),
            sa_func.count(AssessmentAnswer.id).label("question_count"),
        ).where(AssessmentAnswer.attempt_id == attempt_id)
    )
    row = agg.one()
    earned = Decimal(str(float(row.earned or 0)))
    max_possible = Decimal(str(float(row.max_possible or 0)))
    question_count = int(row.question_count or 0)

    if max_possible <= Decimal("0"):
        raise ApiError(
            code="ASSESSMENT_NOT_SCOREABLE",
            message="Assessment has no scoreable answers",
            status_code=409,
        )

    percentage = (earned / max_possible * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    assessment_passed = percentage >= ASSESSMENT_PASS_THRESHOLD

    # Persist score and pass status on attempt
    attempt.score = float(percentage)
    attempt.assessment_passed = bool(assessment_passed)

    # ------------------------------------------------------------------
    # 6. Solidify result timestamp
    # ------------------------------------------------------------------
    attempt.finalized_at = datetime.now(UTC)

    # ------------------------------------------------------------------
    # 7. Provisional or non-formal — never update progress
    # ------------------------------------------------------------------
    if attempt.grading_quality != "final":
        await db.flush()
        return AssessmentFinalizationResult(
            attempt_id=attempt.id,
            grading_quality=attempt.grading_quality or "provisional",
            percentage=percentage,
            assessment_passed=assessment_passed,
            node_completed=False,
            mastery_before=Decimal("0"),
            mastery_after=Decimal("0"),
            mastery_updated=False,
        )

    if assessment.purpose != "formal":
        await db.flush()
        return AssessmentFinalizationResult(
            attempt_id=attempt.id,
            grading_quality="final",
            percentage=percentage,
            assessment_passed=assessment_passed,
            node_completed=False,
            mastery_before=Decimal("0"),
            mastery_after=Decimal("0"),
            mastery_updated=False,
        )

    # ------------------------------------------------------------------
    # 8. Lock path (serialises all finalization on this path)
    # ------------------------------------------------------------------
    path = (
        await db.execute(select(LearningPath).where(LearningPath.id == assessment.path_id).with_for_update())
    ).scalar_one_or_none()
    if not path:
        raise ApiError(code="PATH_NOT_FOUND", message="Learning path not found", status_code=404)

    # 9. Validate assessment belongs to the active version
    if not path.active_version_id:
        raise ApiError(
            code="PATH_NO_ACTIVE_VERSION",
            message="Path has no active version",
            status_code=409,
        )
    if assessment.path_version_id != path.active_version_id:
        raise ApiError(
            code="ASSESSMENT_VERSION_STALE",
            message="Assessment belongs to a different path version than the active one",
            status_code=409,
        )

    # ------------------------------------------------------------------
    # 10. Load (or create) progress FOR UPDATE
    # ------------------------------------------------------------------
    progress = (
        await db.execute(
            select(LearningProgress)
            .where(
                LearningProgress.user_id == attempt.user_id,
                LearningProgress.path_id == assessment.path_id,
                LearningProgress.node_id == assessment.node_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()

    was_completed = progress is not None and progress.status == "completed"
    mastery_before = (
        Decimal(str(progress.mastery)).quantize(Decimal("0.01")) if progress and progress.mastery else Decimal("0")
    )

    # ------------------------------------------------------------------
    # 11. Calculate new mastery
    # ------------------------------------------------------------------
    if progress is None:
        # First-ever assessment for this node — fresh start
        mastery_after = percentage
    else:
        mastery_after = (mastery_before * MASTERY_HISTORY_WEIGHT + percentage * MASTERY_ASSESSMENT_WEIGHT).quantize(
            Decimal("0.01")
        )

    mastery_passed = mastery_after >= NODE_MASTERY_PASS_THRESHOLD

    # Persist mastery on attempt
    attempt.mastery_before = float(mastery_before)
    attempt.mastery_after = float(mastery_after)

    # node_completed is the persisted business field; mastery_passed is the runtime check
    node_completed = bool(mastery_passed)
    attempt.node_completed = node_completed

    # ------------------------------------------------------------------
    # 12. Update learning progress
    # ------------------------------------------------------------------
    if progress is None:
        progress = LearningProgress(
            id=str(uuid.uuid4()),
            user_id=attempt.user_id,
            path_id=assessment.path_id,
            node_id=assessment.node_id,
            status="in_progress",
            mastery=0.0,
            attempts=0,
        )
        db.add(progress)

    progress.mastery = float(mastery_after)
    progress.attempts = (progress.attempts or 0) + 1

    if node_completed:
        progress.status = "completed"
        if not progress.completed_at:
            progress.completed_at = datetime.now(UTC)
    elif not was_completed:
        progress.status = "in_progress"
    # else: was already completed, stays completed (monotonic)

    # ------------------------------------------------------------------
    # 13. Mastery snapshot (linked to attempt, not assessment)
    # ------------------------------------------------------------------
    snapshot = MasterySnapshot(
        id=str(uuid.uuid4()),
        user_id=attempt.user_id,
        node_id=assessment.node_id,
        old_mastery=float(mastery_before),
        new_mastery=float(mastery_after),
        evidence=f"Assessment score: {percentage}%",
        source_type="assessment_attempt",
        source_id=attempt.id,
    )
    db.add(snapshot)

    # ------------------------------------------------------------------
    # 14. Unlock successor nodes (only on newly completed)
    # ------------------------------------------------------------------
    unlocked_node_ids: list[str] = []
    if node_completed and not was_completed:
        unlocked_node_ids = await _unlock_successors(
            db=db,
            user_id=attempt.user_id,
            path_id=assessment.path_id,
            node_id=assessment.node_id,
            version_id=path.active_version_id,
        )

    # ------------------------------------------------------------------
    # 15. Record profile evidence (idempotent upsert)
    # ------------------------------------------------------------------
    profile_evidence_ids = await _record_assessment_evidence(
        db=db,
        user_id=attempt.user_id,
        attempt_id=attempt.id,
        node_id=assessment.node_id,
        percentage=percentage,
        question_count=question_count,
    )

    # ------------------------------------------------------------------
    # 16. Mark progress as applied
    # ------------------------------------------------------------------
    attempt.progress_applied_at = datetime.now(UTC)
    await db.flush()

    return AssessmentFinalizationResult(
        attempt_id=attempt.id,
        grading_quality="final",
        percentage=percentage,
        assessment_passed=assessment_passed,
        node_completed=node_completed,
        mastery_before=mastery_before,
        mastery_after=mastery_after,
        mastery_updated=True,
        unlocked_node_ids=tuple(unlocked_node_ids),
        profile_evidence_ids=tuple(profile_evidence_ids),
    )


async def _unlock_successors(
    db: AsyncSession,
    *,
    user_id: str,
    path_id: str,
    node_id: str,
    version_id: str,
) -> list[str]:
    """Unlock successor nodes where all prerequisites are completed.

    Caller holds the LearningPath FOR UPDATE lock, so concurrent
    finalization on this path never races in this function.
    """
    edges_result = await db.execute(
        select(LearningEdge).where(
            LearningEdge.source_node_id == node_id,
            LearningEdge.version_id == version_id,
        )
    )
    outgoing = list(edges_result.scalars().all())
    unlocked: list[str] = []

    for edge in outgoing:
        target_id = edge.target_node_id

        prereq_result = await db.execute(
            select(LearningEdge).where(
                LearningEdge.target_node_id == target_id,
                LearningEdge.version_id == version_id,
            )
        )
        prereqs = list(prereq_result.scalars().all())
        prereq_source_ids = {e.source_node_id for e in prereqs}

        if prereq_source_ids:
            progress_result = await db.execute(
                select(LearningProgress).where(
                    LearningProgress.user_id == user_id,
                    LearningProgress.path_id == path_id,
                    LearningProgress.node_id.in_(prereq_source_ids),
                )
            )
            completed_ids = {p.node_id for p in progress_result.scalars().all() if p.status == "completed"}
            all_met = prereq_source_ids == completed_ids
        else:
            all_met = True

        if not all_met:
            continue

        target_progress_result = await db.execute(
            select(LearningProgress).where(
                LearningProgress.user_id == user_id,
                LearningProgress.path_id == path_id,
                LearningProgress.node_id == target_id,
            )
        )
        target_progress = target_progress_result.scalar_one_or_none()

        if target_progress and target_progress.status == "locked":
            target_progress.status = "available"
            unlocked.append(target_id)
        elif not target_progress:
            new_progress = LearningProgress(
                id=str(uuid.uuid4()),
                user_id=user_id,
                path_id=path_id,
                node_id=target_id,
                status="available",
            )
            db.add(new_progress)
            unlocked.append(target_id)

    return unlocked


async def _record_assessment_evidence(
    db: AsyncSession,
    *,
    user_id: str,
    attempt_id: str,
    node_id: str,
    percentage: Decimal,
    question_count: int,
) -> list[str]:
    """Record profile evidence dimensions with idempotent upsert.

    PostgreSQL ON CONFLICT DO NOTHING ensures re-entrant safety even
    if the re-entry guard is bypassed (e.g. data repair).
    """
    metadata = {
        "node_id": node_id,
        "percentage": float(percentage),
        "question_count": question_count,
    }

    for dim in EVIDENCE_DIMENSIONS:
        eid = str(uuid.uuid4())
        stmt = (
            pg_insert(StudentProfileEvidence)
            .values(
                id=eid,
                user_id=user_id,
                dimension=dim["dimension"],
                evidence_type="assessment_attempt",
                evidence_id=attempt_id,
                value=float(percentage / Decimal("100")),
                confidence=dim["confidence"],
                evidence_metadata=metadata,
            )
            .on_conflict_do_nothing(
                index_elements=["evidence_type", "evidence_id", "dimension"],
            )
        )
        await db.execute(stmt)

    # Return actual IDs from the database
    result = await db.execute(
        select(StudentProfileEvidence.id).where(
            StudentProfileEvidence.evidence_type == "assessment_attempt",
            StudentProfileEvidence.evidence_id == attempt_id,
        )
    )
    return [r[0] for r in result.all()]


def _build_reentry_result(attempt: AssessmentAttempt) -> AssessmentFinalizationResult:
    """Return the already-persisted result when finalization is re-entered.

    Relies on persisted columns (assessment_passed, node_completed, mastery_*)
    rather than inferred values.  `mastery_updated` is derived from
    `progress_applied_at` — if the learning state was never updated, mastery
    was never modified.
    """
    pct = Decimal(str(attempt.score or 0)).quantize(Decimal("0.01"))
    mastery_updated = attempt.progress_applied_at is not None
    return AssessmentFinalizationResult(
        attempt_id=attempt.id,
        grading_quality=attempt.grading_quality or "final",
        percentage=pct,
        assessment_passed=bool(getattr(attempt, "assessment_passed", False)),
        node_completed=bool(getattr(attempt, "node_completed", False)),
        mastery_before=Decimal(str(attempt.mastery_before or 0)).quantize(Decimal("0.01")),
        mastery_after=Decimal(str(attempt.mastery_after or 0)).quantize(Decimal("0.01")),
        mastery_updated=mastery_updated,
        unlocked_node_ids=(),
        profile_evidence_ids=(),
    )
