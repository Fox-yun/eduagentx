"""Unified learner profile context loader.

Provides a structured, immutable view of a learner's profile for downstream
modules (diagnostic, path planning, unit content, assessment generation,
recommendation).

Contract guarantees:
  - Never contains raw LLM response
  - Never contains internal prompt text
  - Never contains chain-of_thought
  - Only structured dimensions + evidence summary
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import StudentProfile
from app.models.user import StudentProfileEvidence

if TYPE_CHECKING:
    from collections.abc import Mapping

logger = structlog.get_logger()


@dataclass(frozen=True)
class ProfileDimensionValue:
    """A single profile dimension with its value, confidence, and source."""

    value: float | str | list[str] | dict[str, float] | None
    confidence: float
    source: str


@dataclass(frozen=True)
class LearnerProfileContext:
    """Structured learner profile context for downstream modules.

    This is the single, safe data structure that all generation modules
    should consume. It guarantees no internal LLM artifacts leak.
    """

    user_id: str
    dimensions: Mapping[str, ProfileDimensionValue]
    confidence: float
    summary: str
    evidence_summary: tuple[str, ...]
    profile_version: int
    status: str

    # Convenience accessors for common dimension checks ---------------------

    @property
    def knowledge_depth(self) -> ProfileDimensionValue | None:
        return self.dimensions.get("knowledge_depth")

    @property
    def prerequisite_mastery(self) -> ProfileDimensionValue | None:
        return self.dimensions.get("prerequisite_mastery")

    @property
    def concept_grasp(self) -> ProfileDimensionValue | None:
        return self.dimensions.get("concept_grasp")

    @property
    def problem_solving(self) -> ProfileDimensionValue | None:
        return self.dimensions.get("problem_solving")

    @property
    def practice_ability(self) -> ProfileDimensionValue | None:
        return self.dimensions.get("practice_ability")

    @property
    def learning_pace(self) -> ProfileDimensionValue | None:
        return self.dimensions.get("learning_pace")

    @property
    def resource_preference(self) -> ProfileDimensionValue | None:
        return self.dimensions.get("resource_preference")

    @property
    def error_pattern(self) -> ProfileDimensionValue | None:
        return self.dimensions.get("error_pattern")

    # Helper predicates ------------------------------------------------------

    @property
    def is_weak_foundation(self) -> bool:
        """True if knowledge_depth < 0.4 or prerequisite_mastery < 0.4."""
        kd = self.knowledge_depth
        pm = self.prerequisite_mastery
        kd_low = isinstance(kd.value, (int, float)) and kd.value < 0.4 if kd else False
        pm_low = isinstance(pm.value, (int, float)) and pm.value < 0.4 if pm else False
        return kd_low or pm_low

    @property
    def is_slow_pace(self) -> bool:
        """True if learning_pace is 'slow'."""
        lp = self.learning_pace
        return lp is not None and lp.value == "slow"

    @property
    def prefers_project(self) -> bool:
        """True if resource_preference includes 'project'."""
        rp = self.resource_preference
        return rp is not None and isinstance(rp.value, list) and "project" in rp.value

    @property
    def prefers_code(self) -> bool:
        """True if resource_preference includes 'code' or 'reading'."""
        rp = self.resource_preference
        if rp is None or not isinstance(rp.value, list):
            return False
        return any(p in rp.value for p in ("code", "reading"))

    @property
    def error_patterns(self) -> list[str]:
        """List of error pattern keys with value > 0.3."""
        ep = self.error_pattern
        if ep is None or not isinstance(ep.value, dict):
            return []
        return [k for k, v in ep.value.items() if isinstance(v, (int, float)) and v > 0.3]

    def to_prompt_string(self) -> str:
        """Format as a context block suitable for LLM prompts.

        This is the ONLY method that produces text for LLM consumption.
        It includes only structured dimension data — no prompts, no CoT,
        no raw LLM responses.
        """
        labels = {
            "knowledge_depth": "知识深度",
            "prerequisite_mastery": "前置知识掌握度",
            "concept_grasp": "概念理解力",
            "problem_solving": "问题解决能力",
            "practice_ability": "实践能力",
            "learning_pace": "学习节奏",
            "resource_preference": "资源偏好",
            "error_pattern": "常见错误模式",
        }

        lines: list[str] = ["## 学习者画像（请参考以下信息个性化生成内容）"]

        for dim_name, label in labels.items():
            dim = self.dimensions.get(dim_name)
            if dim is None:
                continue
            value = dim.value
            confidence = dim.confidence
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

        if self.summary:
            lines.append(f"\n画像摘要: {self.summary}")

        return "\n".join(lines)


async def load_learner_profile_context(
    db: AsyncSession,
    *,
    user_id: str,
) -> LearnerProfileContext | None:
    """Load a structured learner profile context.

    Returns ``None`` when no profile exists or the profile has no dimensions.
    Downstream modules should treat ``None`` as "no profile available" and
    fall back to default generation strategies.

    Guarantees:
      - The returned object never contains raw LLM response, prompts,
        or chain-of-thought.
      - Only structured dimensions and evidence summaries are included.
    """
    result = await db.execute(select(StudentProfile).where(StudentProfile.user_id == user_id))
    profile = result.scalar_one_or_none()
    if not profile or not profile.dimensions:
        return None

    # Build dimension mapping
    dimensions: dict[str, ProfileDimensionValue] = {}
    for dim_name, dim_data in (profile.dimensions or {}).items():
        if not isinstance(dim_data, dict):
            continue
        dimensions[dim_name] = ProfileDimensionValue(
            value=dim_data.get("value"),
            confidence=float(dim_data.get("confidence", 0.0)),
            source=str(dim_data.get("source", "")),
        )

    # Build evidence summary (type + dimension, no raw content)
    evidence_result = await db.execute(
        select(StudentProfileEvidence)
        .where(StudentProfileEvidence.user_id == user_id)
        .order_by(StudentProfileEvidence.created_at.desc())
        .limit(20)
    )
    evidence_rows = list(evidence_result.scalars().all())
    evidence_summary = tuple(
        f"{e.evidence_type}:{e.dimension}" for e in evidence_rows
    )

    return LearnerProfileContext(
        user_id=user_id,
        dimensions=dimensions,
        confidence=float(profile.confidence),
        summary=profile.summary or "",
        evidence_summary=evidence_summary,
        profile_version=profile.profile_version,
        status=profile.status,
    )
