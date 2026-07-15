"""Learning behaviour capture and low-confidence profile evidence mapping."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import ProfileEvidenceType
from app.core.errors import ApiError
from app.models.path import LearningNode, LearningPath
from app.models.progress import LearningEvent
from app.services.profile_merge import ProfileEvidenceInput, apply_profile_evidence

if TYPE_CHECKING:
    from datetime import datetime

RESOURCE_PREFERENCES: dict[str, list[str]] = {
    "lecture": ["reading"],
    "mindmap": ["visual"],
    "pptx": ["visual", "reading"],
    "video": ["video", "visual"],
    "code_zip": ["code", "project"],
    "interactive_cards": ["interactive"],
    "walkthrough": ["project", "reading"],
    "simulation": ["interactive", "visual"],
}


async def record_learning_event(
    db: AsyncSession,
    *,
    user_id: str,
    path_id: str,
    node_id: str | None,
    event_type: str,
    resource_type: str | None,
    duration_seconds: int | None,
    client_event_id: str | None,
    event_metadata: dict[str, Any] | None,
    occurred_at: datetime,
) -> tuple[LearningEvent, int | None, bool]:
    """Validate ownership, persist an idempotent event, and merge safe evidence."""
    path = (
        await db.execute(select(LearningPath).where(LearningPath.id == path_id, LearningPath.user_id == user_id))
    ).scalar_one_or_none()
    if path is None:
        raise ApiError(code="PATH_NOT_FOUND", message="Learning path not found", status_code=404)

    if node_id:
        node = (
            await db.execute(
                select(LearningNode).where(
                    LearningNode.id == node_id,
                    LearningNode.version_id == path.active_version_id,
                )
            )
        ).scalar_one_or_none()
        if node is None:
            raise ApiError(code="NODE_NOT_FOUND", message="Learning node not found", status_code=404)

    if client_event_id:
        existing = (
            await db.execute(
                select(LearningEvent).where(
                    LearningEvent.user_id == user_id,
                    LearningEvent.client_event_id == client_event_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing, None, False

    event = LearningEvent(
        user_id=user_id,
        path_id=path_id,
        node_id=node_id,
        event_type=event_type,
        resource_type=resource_type,
        duration_seconds=duration_seconds,
        client_event_id=client_event_id,
        event_metadata=event_metadata or {},
        occurred_at=occurred_at,
    )
    db.add(event)
    await db.flush()

    evidence = _event_evidence(event)
    profile_version: int | None = None
    if evidence:
        profile = await apply_profile_evidence(db, user_id=user_id, evidence=evidence)
        profile_version = profile.profile_version

    return event, profile_version, True


def _event_evidence(event: LearningEvent) -> list[ProfileEvidenceInput]:
    """Map only behaviour that has a defensible learner-profile signal."""
    evidence: list[ProfileEvidenceInput] = []
    metadata = event.event_metadata or {}
    evidence_id = event.id

    preferences = RESOURCE_PREFERENCES.get(event.resource_type or "")
    if event.event_type in {"resource_opened", "resource_completed", "resource_downloaded"} and preferences:
        confidence = 0.48 if event.event_type == "resource_completed" else 0.36
        evidence.append(
            ProfileEvidenceInput(
                dimension="resource_preference",
                value=preferences,
                confidence=confidence,
                evidence_type=ProfileEvidenceType.LEARNING_BEHAVIOR.value,
                evidence_id=evidence_id,
                evidence_text=f"Used learning resource: {event.resource_type}",
                metadata={"event_type": event.event_type, "path_id": event.path_id, "node_id": event.node_id},
            )
        )

    score = metadata.get("score")
    if event.event_type == "practice_completed" and isinstance(score, (int, float)):
        normalized = max(0.0, min(float(score) / 100.0, 1.0))
        evidence.append(
            ProfileEvidenceInput(
                dimension="practice_ability",
                value=normalized,
                confidence=0.58,
                evidence_type=ProfileEvidenceType.LEARNING_BEHAVIOR.value,
                evidence_id=evidence_id,
                evidence_text=f"Practice completion score: {float(score):.1f}%",
                metadata={"path_id": event.path_id, "node_id": event.node_id},
            )
        )

    if event.event_type == "tutor_feedback" and metadata.get("helpful") is True:
        mode_preferences = {
            "diagram": "visual",
            "code": "code",
            "storyboard": "video",
        }
        preferred_modes = metadata.get("response_modes")
        if isinstance(preferred_modes, list):
            preferences = [mode_preferences[mode] for mode in preferred_modes if mode in mode_preferences]
            if preferences:
                evidence.append(
                    ProfileEvidenceInput(
                        dimension="resource_preference",
                        value=preferences,
                        confidence=0.42,
                        evidence_type=ProfileEvidenceType.LEARNING_BEHAVIOR.value,
                        evidence_id=evidence_id,
                        evidence_text=f"Helpful tutor modalities: {', '.join(preferred_modes)}",
                        metadata={"path_id": event.path_id, "node_id": event.node_id},
                    )
                )

    return evidence
