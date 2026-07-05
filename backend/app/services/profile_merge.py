"""Profile merge service — weighted evidence merging into StudentProfile.

Phase 3.6-C: Provides a standalone service for merging evidence from
multiple sources (assessment, diagnostic, conversation, manual correction)
into the StudentProfile using confidence-weighted formulas.

Merge rules:
  - Numeric dimensions (knowledge_depth, prerequisite_mastery, etc.):
      merged = (old * old_conf + new * new_conf) / (old_conf + new_conf)
  - Enum/preference dimensions (resource_preference, learning_pace):
      Weighted counting, sorted by frequency
  - Error pattern (error_pattern):
      Dict accumulation with decay
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import PROFILE_DIMENSIONS, ProfileEvidenceType, ProfileStatus
from app.models.profile import StudentProfile
from app.models.user import StudentProfileEvidence

logger = structlog.get_logger()


@dataclass(frozen=True)
class ProfileEvidenceInput:
    """Input for a single evidence record to merge into the profile.

    Attributes:
        dimension: One of the 8 core dimensions
        value: Numeric value (0-1), string, list, or dict
        confidence: Confidence score in [0, 1]
        evidence_type: One of ProfileEvidenceType
        evidence_id: Unique ID for the source (attempt_id, session_id, etc.)
        evidence_text: Optional human-readable evidence summary
        metadata: Optional additional metadata
    """

    dimension: str
    value: float | str | list[str] | dict[str, float]
    confidence: float
    evidence_type: str
    evidence_id: str
    evidence_text: str = ""
    metadata: dict[str, Any] | None = None


async def apply_profile_evidence(
    db: AsyncSession,
    *,
    user_id: str,
    evidence: list[ProfileEvidenceInput],
) -> StudentProfile:
    """Apply multiple evidence records to a student profile.

    This is the single entry point for all profile updates from
    assessment, diagnostic, conversation, and manual correction sources.

    Args:
        db: Async database session
        user_id: User ID
        evidence: List of evidence inputs to merge

    Returns:
        Updated StudentProfile
    """
    profile = await _get_or_create_profile(db, user_id)

    # E0-A4: Check evidence existence BEFORE merging to ensure idempotency.
    # Only new (non-existing) evidence items participate in the merge and
    # are written to the database.  profile_version only increments when
    # at least one new evidence item is added.
    new_evidence_items: list[ProfileEvidenceInput] = []

    for ev in evidence:
        if ev.dimension not in PROFILE_DIMENSIONS:
            logger.warning("profile_merge_skip_invalid_dimension", dimension=ev.dimension)
            continue

        existing = await db.execute(
            select(StudentProfileEvidence.id).where(
                StudentProfileEvidence.user_id == user_id,
                StudentProfileEvidence.evidence_type == ev.evidence_type,
                StudentProfileEvidence.evidence_id == ev.evidence_id,
                StudentProfileEvidence.dimension == ev.dimension,
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue

        new_evidence_items.append(ev)

    if not new_evidence_items:
        # All evidence already exists — return profile unchanged
        return profile

    # Merge only new evidence into profile dimensions
    # E0-A2: copy-then-assign for JSON persistence
    dims = dict(profile.dimensions or {})

    for ev in new_evidence_items:
        current = dims.get(ev.dimension, {})
        old_value = current.get("value")
        old_confidence = current.get("confidence", 0.0)

        merged_value = _merge_values(old_value, old_confidence, ev.value, ev.confidence, ev.dimension)

        dims[ev.dimension] = {
            "value": merged_value,
            "confidence": max(old_confidence, ev.confidence),
            "source": ev.evidence_type,
        }

        # Write evidence record
        evidence_record = StudentProfileEvidence(
            id=str(uuid.uuid4()),
            user_id=user_id,
            dimension=ev.dimension,
            evidence_type=ev.evidence_type,
            evidence_id=ev.evidence_id,
            value=float(ev.value) if isinstance(ev.value, (int, float)) else 0.0,
            confidence=ev.confidence,
            evidence_metadata={
                "evidence_text": ev.evidence_text,
                "raw_value": ev.value,
                **(ev.metadata or {}),
            },
        )
        db.add(evidence_record)

    profile.dimensions = dims

    # Update profile metadata — only when new evidence was added
    profile.profile_version += 1
    profile.confidence = _average_confidence(profile.dimensions)

    # If low confidence, mark as provisional
    if profile.confidence < 0.65:
        profile.status = ProfileStatus.PROVISIONAL.value
    elif profile.status == ProfileStatus.PROVISIONAL.value:
        profile.status = ProfileStatus.ACTIVE.value

    await db.flush()

    logger.info(
        "profile_evidence_applied",
        user_id=user_id,
        profile_id=profile.id,
        version=profile.profile_version,
        evidence_count=len(new_evidence_items),
        confidence=profile.confidence,
    )

    return profile


async def apply_assessment_evidence(
    db: AsyncSession,
    *,
    user_id: str,
    attempt_id: str,
    score: float,
    passed: bool,
    node_title: str,
    weak_concepts: list[str] | None = None,
) -> StudentProfile:
    """Apply assessment result as profile evidence.

    Updates knowledge_depth, concept_grasp, problem_solving, and
    practice_ability based on assessment score.
    """
    # Normalize score to 0-1 range
    normalized_score = score / 100.0

    evidence: list[ProfileEvidenceInput] = [
        ProfileEvidenceInput(
            dimension="knowledge_depth",
            value=normalized_score,
            confidence=0.78,
            evidence_type=ProfileEvidenceType.ASSESSMENT_ATTEMPT.value,
            evidence_id=attempt_id,
            evidence_text=f"Assessment score: {score:.1f}% on '{node_title}'",
            metadata={"node_title": node_title, "passed": passed},
        ),
        ProfileEvidenceInput(
            dimension="concept_grasp",
            value=normalized_score,
            confidence=0.84,
            evidence_type=ProfileEvidenceType.ASSESSMENT_ATTEMPT.value,
            evidence_id=attempt_id,
            evidence_text=f"Concept understanding: {score:.1f}%",
            metadata={"node_title": node_title, "passed": passed},
        ),
        ProfileEvidenceInput(
            dimension="problem_solving",
            value=normalized_score * (0.9 if passed else 0.6),
            confidence=0.72,
            evidence_type=ProfileEvidenceType.ASSESSMENT_ATTEMPT.value,
            evidence_id=attempt_id,
            evidence_text=f"Problem-solving: {'passed' if passed else 'failed'}",
            metadata={"node_title": node_title, "passed": passed},
        ),
        ProfileEvidenceInput(
            dimension="practice_ability",
            value=normalized_score * (0.85 if passed else 0.5),
            confidence=0.68,
            evidence_type=ProfileEvidenceType.ASSESSMENT_ATTEMPT.value,
            evidence_id=attempt_id,
            evidence_text=f"Practice ability: {score:.1f}%",
            metadata={"node_title": node_title, "passed": passed},
        ),
    ]

    # Add error pattern from weak concepts
    if weak_concepts:
        error_dict: dict[str, float] = {concept: 0.7 for concept in weak_concepts}
        evidence.append(
            ProfileEvidenceInput(
                dimension="error_pattern",
                value=error_dict,
                confidence=0.65,
                evidence_type=ProfileEvidenceType.ASSESSMENT_ATTEMPT.value,
                evidence_id=attempt_id,
                evidence_text=f"Weak concepts: {', '.join(weak_concepts)}",
                metadata={"weak_concepts": weak_concepts},
            )
        )

    return await apply_profile_evidence(db, user_id=user_id, evidence=evidence)


async def apply_diagnostic_evidence(
    db: AsyncSession,
    *,
    user_id: str,
    attempt_id: str,
    percentage: float,
    weak_areas: list[str] | None = None,
) -> StudentProfile:
    """Apply diagnostic result as profile evidence.

    Updates knowledge_depth and prerequisite_mastery based on diagnostic score.
    """
    normalized = percentage / 100.0

    evidence: list[ProfileEvidenceInput] = [
        ProfileEvidenceInput(
            dimension="knowledge_depth",
            value=normalized,
            confidence=0.80,
            evidence_type=ProfileEvidenceType.DIAGNOSTIC_RESULT.value,
            evidence_id=attempt_id,
            evidence_text=f"Diagnostic score: {percentage:.1f}%",
        ),
        ProfileEvidenceInput(
            dimension="prerequisite_mastery",
            value=normalized * 0.9,
            confidence=0.75,
            evidence_type=ProfileEvidenceType.DIAGNOSTIC_RESULT.value,
            evidence_id=attempt_id,
            evidence_text=f"Prerequisite mastery: {percentage:.1f}%",
        ),
    ]

    if weak_areas:
        error_dict = {area: 0.8 for area in weak_areas}
        evidence.append(
            ProfileEvidenceInput(
                dimension="error_pattern",
                value=error_dict,
                confidence=0.70,
                evidence_type=ProfileEvidenceType.DIAGNOSTIC_RESULT.value,
                evidence_id=attempt_id,
                evidence_text=f"Diagnostic weak areas: {', '.join(weak_areas)}",
                metadata={"weak_areas": weak_areas},
            )
        )

    return await apply_profile_evidence(db, user_id=user_id, evidence=evidence)


# ------------------------------------------------------------------
# Private helpers
# ------------------------------------------------------------------


def _merge_values(
    old_value: Any,
    old_confidence: float,
    new_value: Any,
    new_confidence: float,
    dimension: str,
) -> Any:
    """Merge old and new values based on dimension type."""
    # Numeric dimensions: weighted average
    if isinstance(new_value, (int, float)) and isinstance(old_value, (int, float)):
        total_conf = old_confidence + new_confidence
        if total_conf > 0:
            return (old_value * old_confidence + new_value * new_confidence) / total_conf
        return new_value

    # If old value doesn't exist, use new value
    if old_value is None:
        return new_value

    # List dimensions (resource_preference): merge with frequency counting
    if isinstance(new_value, list) and isinstance(old_value, list):
        # Count occurrences with confidence weighting
        counts: dict[str, float] = {}
        for item in old_value:
            counts[str(item)] = counts.get(str(item), 0) + old_confidence
        for item in new_value:
            counts[str(item)] = counts.get(str(item), 0) + new_confidence
        # Sort by weighted count, return top items
        sorted_items = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        return [item for item, _ in sorted_items[:5]]

    # Dict dimensions (error_pattern): accumulate with decay
    if isinstance(new_value, dict) and isinstance(old_value, dict):
        merged: dict[str, float] = {}
        # Decay old values
        for k, v in old_value.items():
            merged[k] = float(v) * 0.85  # 15% decay
        # Add new values
        for k, v in new_value.items():
            merged[k] = merged.get(k, 0) + float(v) * new_confidence
        # Keep only non-trivial entries
        return {k: v for k, v in merged.items() if v > 0.1}

    # String dimensions (learning_pace): use new if higher confidence
    if new_confidence >= old_confidence:
        return new_value
    return old_value


def _average_confidence(dimensions: dict[str, Any]) -> float:
    """Calculate average confidence across all dimensions."""
    if not dimensions:
        return 0.0
    confidences = [d.get("confidence", 0) for d in dimensions.values()]
    return sum(confidences) / len(confidences) if confidences else 0.0


async def _get_or_create_profile(db: AsyncSession, user_id: str) -> StudentProfile:
    """Get existing profile or create a new one."""
    result = await db.execute(select(StudentProfile).where(StudentProfile.user_id == user_id))
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = StudentProfile(
            id=str(uuid.uuid4()),
            user_id=user_id,
            status=ProfileStatus.ACTIVE.value,
            profile_version=0,
            dimensions={},
            confidence=0.0,
        )
        db.add(profile)
        await db.flush()
    return profile


# ------------------------------------------------------------------
# Profile context helpers — shared by path/unit/assessment/recommendation
# ------------------------------------------------------------------

# Human-readable labels for the 8 dimensions
_DIMENSION_LABELS: dict[str, str] = {
    "knowledge_depth": "知识深度",
    "prerequisite_mastery": "先修知识掌握",
    "concept_grasp": "概念理解能力",
    "problem_solving": "问题解决能力",
    "practice_ability": "实践能力",
    "learning_pace": "学习节奏",
    "resource_preference": "资源偏好",
    "error_pattern": "常见错误模式",
}


async def load_profile_context(
    db: AsyncSession,
    user_id: str,
) -> tuple[StudentProfile | None, str]:
    """Load a student profile and format it as a context string for LLM prompts.

    Returns ``(profile, context_string)`` where *context_string* is an
    empty string when no profile exists or the profile has no dimensions.
    Downstream services (path planning, unit content, assessment generation)
    use this to personalise LLM prompts.
    """
    result = await db.execute(select(StudentProfile).where(StudentProfile.user_id == user_id))
    profile = result.scalar_one_or_none()
    if not profile or not profile.dimensions:
        return None, ""
    return profile, _format_profile_for_prompt(profile)


def _format_profile_for_prompt(profile: StudentProfile) -> str:
    """Format profile dimensions as a context block suitable for LLM prompts."""
    lines: list[str] = ["## 学习者画像（请参考以下信息个性化生成内容）"]

    for dim_name, label in _DIMENSION_LABELS.items():
        dim_data = profile.dimensions.get(dim_name)
        if not dim_data:
            continue
        value = dim_data.get("value")
        confidence = dim_data.get("confidence", 0)
        if value is None:
            continue
        if isinstance(value, float):
            lines.append(f"- {label}: {value:.2f}（置信度 {confidence:.0%}）")
        elif isinstance(value, list):
            lines.append(f"- {label}: {', '.join(str(v) for v in value)}")
        elif isinstance(value, dict):
            items = ", ".join(f"{k}={v:.1f}" for k, v in value.items())
            lines.append(f"- {label}: {items}")
        else:
            lines.append(f"- {label}: {value}")

    if profile.summary:
        lines.append(f"\n画像摘要: {profile.summary}")

    return "\n".join(lines)
