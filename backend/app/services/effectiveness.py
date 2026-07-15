"""Path-level learning effectiveness aggregation and explainable evaluation."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.models.path import LearningNode, LearningPath, LearningPathVersion
from app.models.profile import StudentProfile
from app.models.progress import (
    LearningEvent,
    LearningPathAdaptationProposal,
    LearningProgress,
    MasterySnapshot,
)
from app.models.unit import Assessment, AssessmentAttempt
from app.models.user import StudentProfileEvidence


async def get_learning_effectiveness(
    db: AsyncSession,
    *,
    user_id: str,
    path_id: str,
) -> dict[str, Any]:
    """Aggregate behaviour, progress, assessment, and profile evidence for one path."""
    path = (
        await db.execute(select(LearningPath).where(LearningPath.id == path_id, LearningPath.user_id == user_id))
    ).scalar_one_or_none()
    if path is None:
        raise ApiError(code="PATH_NOT_FOUND", message="Learning path not found", status_code=404)

    nodes = list(
        (
            await db.execute(
                select(LearningNode)
                .where(LearningNode.version_id == path.active_version_id)
                .order_by(LearningNode.node_order)
            )
        )
        .scalars()
        .all()
    )
    node_ids = [node.id for node in nodes]

    progress_items = list(
        (
            await db.execute(
                select(LearningProgress).where(
                    LearningProgress.user_id == user_id,
                    LearningProgress.path_id == path_id,
                    LearningProgress.node_id.in_(node_ids) if node_ids else False,  # type: ignore[arg-type]
                )
            )
        )
        .scalars()
        .all()
    )
    progress_by_node = {item.node_id: item for item in progress_items}

    events = list(
        (
            await db.execute(
                select(LearningEvent).where(
                    LearningEvent.user_id == user_id,
                    LearningEvent.path_id == path_id,
                )
            )
        )
        .scalars()
        .all()
    )
    attempts = list(
        (
            await db.execute(
                select(AssessmentAttempt, Assessment)
                .join(Assessment, Assessment.id == AssessmentAttempt.assessment_id)
                .where(
                    AssessmentAttempt.user_id == user_id,
                    Assessment.path_id == path_id,
                    AssessmentAttempt.finalized_at.is_not(None),
                )
                .order_by(AssessmentAttempt.finalized_at)
            )
        ).all()
    )
    snapshots = list(
        (
            await db.execute(
                select(MasterySnapshot)
                .where(
                    MasterySnapshot.user_id == user_id,
                    MasterySnapshot.node_id.in_(node_ids) if node_ids else False,  # type: ignore[arg-type]
                )
                .order_by(MasterySnapshot.created_at)
            )
        )
        .scalars()
        .all()
    )
    profile = (await db.execute(select(StudentProfile).where(StudentProfile.user_id == user_id))).scalar_one_or_none()
    evidence = list(
        (
            await db.execute(
                select(StudentProfileEvidence)
                .where(StudentProfileEvidence.user_id == user_id)
                .order_by(StudentProfileEvidence.created_at.desc())
                .limit(8)
            )
        )
        .scalars()
        .all()
    )
    proposals = list(
        (
            await db.execute(
                select(LearningPathAdaptationProposal)
                .where(
                    LearningPathAdaptationProposal.user_id == user_id,
                    LearningPathAdaptationProposal.path_id == path_id,
                )
                .order_by(LearningPathAdaptationProposal.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    versions = list(
        (
            await db.execute(
                select(LearningPathVersion)
                .where(LearningPathVersion.path_id == path_id)
                .order_by(LearningPathVersion.version_number)
            )
        )
        .scalars()
        .all()
    )

    completed_nodes = sum(
        1 for node in nodes if progress_by_node.get(node.id) and progress_by_node[node.id].status == "completed"
    )
    masteries = [progress_by_node[node.id].mastery for node in nodes if node.id in progress_by_node]
    formal_attempts = [attempt for attempt, assessment in attempts if assessment.purpose == "formal"]
    passing_attempts = [attempt for attempt in formal_attempts if bool(attempt.assessment_passed)]
    scores = [float(attempt.score) for attempt in formal_attempts if attempt.score is not None]
    total_duration = sum(int(event.duration_seconds or 0) for event in events)

    resource_stats: dict[str, dict[str, int]] = {}
    for event in events:
        if not event.resource_type:
            continue
        stat = resource_stats.setdefault(event.resource_type, {"opens": 0, "duration_seconds": 0})
        if event.event_type == "resource_opened":
            stat["opens"] += 1
        stat["duration_seconds"] += int(event.duration_seconds or 0)

    overview = {
        "total_nodes": len(nodes),
        "completed_nodes": completed_nodes,
        "completion_rate": _ratio(completed_nodes, len(nodes)),
        "learning_minutes": round(total_duration / 60, 1),
        "assessment_count": len(formal_attempts),
        "assessment_pass_rate": _ratio(len(passing_attempts), len(formal_attempts)),
        "average_score": round(sum(scores) / len(scores), 1) if scores else 0.0,
        "average_mastery": round(sum(masteries) / len(masteries), 1) if masteries else 0.0,
    }
    rating = _rating(overview, bool(events or attempts or progress_items))

    error_pattern = ((profile.dimensions or {}).get("error_pattern", {}).get("value", {})) if profile else {}
    weak_points = []
    if isinstance(error_pattern, dict):
        weak_points = [
            {"name": str(name), "weight": round(float(weight), 2)}
            for name, weight in sorted(error_pattern.items(), key=lambda item: float(item[1]), reverse=True)[:5]
        ]

    return {
        "path_id": path_id,
        "rating": rating,
        "overview": overview,
        "resource_usage": [
            {
                "resource_type": resource_type,
                "opens": values["opens"],
                "duration_minutes": round(values["duration_seconds"] / 60, 1),
            }
            for resource_type, values in sorted(
                resource_stats.items(), key=lambda item: (item[1]["duration_seconds"], item[1]["opens"]), reverse=True
            )
        ],
        "mastery_trend": [
            {
                "node_id": snapshot.node_id,
                "mastery": round(snapshot.new_mastery, 1),
                "recorded_at": snapshot.created_at.isoformat(),
            }
            for snapshot in snapshots[-20:]
        ],
        "node_performance": [
            {
                "node_id": node.id,
                "title": node.title,
                "status": progress_by_node[node.id].status if node.id in progress_by_node else node.status,
                "mastery": round(progress_by_node[node.id].mastery, 1) if node.id in progress_by_node else 0.0,
                "attempts": progress_by_node[node.id].attempts if node.id in progress_by_node else 0,
            }
            for node in nodes
        ],
        "weak_points": weak_points,
        "profile": {
            "version": profile.profile_version if profile else 0,
            "confidence": round(profile.confidence, 2) if profile else 0.0,
            "recent_evidence": [
                {
                    "dimension": item.dimension,
                    "evidence_type": item.evidence_type,
                    "confidence": round(item.confidence, 2),
                    "evidence_text": (item.evidence_metadata or {}).get("evidence_text", ""),
                    "created_at": item.created_at.isoformat(),
                }
                for item in evidence
            ],
        },
        "adaptation": {
            "proposal_count": len(proposals),
            "open_count": sum(1 for item in proposals if item.status == "proposed"),
            "accepted_count": sum(1 for item in proposals if item.status == "accepted"),
            "latest_reason": proposals[0].reason if proposals else None,
            "latest_evidence": proposals[0].evidence if proposals else None,
        },
        "path_versions": {
            "current_version": next(
                (version.version_number for version in versions if version.id == path.active_version_id), 0
            ),
            "total_versions": len(versions),
            "latest_summary": versions[-1].summary if versions else None,
        },
        "suggestions": _suggestions(overview, weak_points, resource_stats),
    }


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator * 100, 1) if denominator else 0.0


def _rating(overview: dict[str, Any], has_data: bool) -> str:
    if not has_data:
        return "insufficient_data"
    score = (
        float(overview["completion_rate"]) * 0.35
        + float(overview["assessment_pass_rate"]) * 0.35
        + float(overview["average_mastery"]) * 0.30
    )
    if score >= 80:
        return "excellent"
    if score >= 55:
        return "steady"
    return "needs_attention"


def _suggestions(
    overview: dict[str, Any], weak_points: list[dict[str, Any]], resource_stats: dict[str, Any]
) -> list[str]:
    suggestions: list[str] = []
    if overview["assessment_count"] == 0:
        suggestions.append("完成至少一次正式评估，建立可量化的掌握度基线。")
    elif overview["assessment_pass_rate"] < 60:
        suggestions.append("优先复习最近未通过的知识节点，再进行一次针对性练习。")
    if weak_points:
        suggestions.append(f"重点巩固薄弱点：{'、'.join(item['name'] for item in weak_points[:3])}。")
    if not resource_stats:
        suggestions.append("结合讲义与思维导图学习，系统会根据实际使用情况优化资源推荐。")
    if overview["completion_rate"] >= 80 and overview["assessment_pass_rate"] >= 80:
        suggestions.append("当前学习效果稳定，可以进入综合项目或更高难度拓展任务。")
    return suggestions[:4]
