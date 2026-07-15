"""Integration coverage for behaviour evidence, feedback ranking, and adaptations."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.models.goal import LearningGoal
from app.models.path import LearningNode, LearningPath, LearningPathVersion
from app.models.progress import (
    LearningEvent,
    LearningPathAdaptationProposal,
    LearningProgress,
    MasterySnapshot,
    RecommendationFeedback,
)
from app.models.unit import Assessment, AssessmentAttempt
from app.models.user import User
from app.services.adaptation import ensure_failure_adaptation_proposal
from app.services.effectiveness import get_learning_effectiveness
from app.services.learning_behavior import record_learning_event
from app.services.profile_merge import ProfileEvidenceInput, apply_profile_evidence
from app.services.recommendations import RecommendationService


async def _learning_context(db_session):
    user_id = str(uuid.uuid4())
    goal_id = str(uuid.uuid4())
    path_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    node_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    db_session.add(
        User(
            id=user_id,
            email=f"behavior-{user_id[:8]}@example.com",
            email_normalized=f"behavior-{user_id[:8]}@example.com",
            display_name="Behavior Learner",
            password_hash="hash",
            status="active",
            email_verified_at=datetime.now(UTC),
        )
    )
    await db_session.flush()
    db_session.add(
        LearningGoal(
            id=goal_id,
            user_id=user_id,
            raw_description="学习 Python",
            normalized_goal="Python",
            title="Python",
            current_level="beginner",
            target_level="intermediate",
            status="planning",
        )
    )
    await db_session.flush()
    db_session.add(
        LearningPath(
            id=path_id,
            user_id=user_id,
            goal_id=goal_id,
            active_version_id=version_id,
            status="active",
        )
    )
    await db_session.flush()
    db_session.add(
        LearningPathVersion(
            id=version_id,
            path_id=path_id,
            version_number=1,
            status="active",
            created_by="system",
        )
    )
    await db_session.flush()
    for index, node_id in enumerate(node_ids):
        db_session.add(
            LearningNode(
                id=node_id,
                version_id=version_id,
                title=f"Node {index + 1}",
                node_order=index,
                difficulty="beginner",
                estimated_minutes=20,
                status="available",
                mastery=0,
            )
        )
    await db_session.commit()
    return user_id, path_id, version_id, node_ids


async def test_resource_event_updates_profile_and_is_idempotent(db_session):
    user_id, path_id, _version_id, node_ids = await _learning_context(db_session)
    event, version, created = await record_learning_event(
        db_session,
        user_id=user_id,
        path_id=path_id,
        node_id=node_ids[0],
        event_type="resource_opened",
        resource_type="mindmap",
        duration_seconds=None,
        client_event_id="mindmap-once",
        event_metadata={},
        occurred_at=datetime.now(UTC),
    )
    await db_session.commit()
    assert created is True
    assert version == 1

    duplicate, duplicate_version, duplicate_created = await record_learning_event(
        db_session,
        user_id=user_id,
        path_id=path_id,
        node_id=node_ids[0],
        event_type="resource_opened",
        resource_type="mindmap",
        duration_seconds=None,
        client_event_id="mindmap-once",
        event_metadata={},
        occurred_at=datetime.now(UTC),
    )
    assert duplicate.id == event.id
    assert duplicate_version is None
    assert duplicate_created is False


async def test_recommendation_feedback_changes_ranking_and_visibility(db_session):
    user_id, path_id, _version_id, node_ids = await _learning_context(db_session)
    db_session.add(
        RecommendationFeedback(
            user_id=user_id,
            path_id=path_id,
            recommendation_key=f"continue:{node_ids[0]}",
            recommendation_type="continue",
            node_id=node_ids[0],
            action="ignore",
        )
    )
    await db_session.commit()
    recommendations = await RecommendationService(db_session).get_recommendations(path_id, user_id)
    assert all(item["feedback_key"] != f"continue:{node_ids[0]}" for item in recommendations)


async def test_consecutive_failures_create_only_a_proposal(db_session):
    user_id, path_id, version_id, node_ids = await _learning_context(db_session)
    for index, node_id in enumerate(node_ids):
        assessment_id = str(uuid.uuid4())
        db_session.add(
            Assessment(
                id=assessment_id,
                user_id=user_id,
                path_id=path_id,
                path_version_id=version_id,
                node_id=node_id,
                purpose="formal",
                status="ready",
            )
        )
        db_session.add(
            AssessmentAttempt(
                id=str(uuid.uuid4()),
                assessment_id=assessment_id,
                user_id=user_id,
                status="completed",
                score=35 + index,
                passed=False,
                assessment_passed=False,
                finalized_at=datetime.now(UTC),
            )
        )
    await db_session.flush()

    proposal = await ensure_failure_adaptation_proposal(
        db_session,
        user_id=user_id,
        path_id=path_id,
        trigger_node_id=node_ids[-1],
    )
    assert proposal is not None
    assert proposal.status == "proposed"
    assert proposal.revision_request_id is None
    assert len(proposal.evidence["attempt_ids"]) == 2

    same_proposal = await ensure_failure_adaptation_proposal(
        db_session,
        user_id=user_id,
        path_id=path_id,
        trigger_node_id=node_ids[-1],
    )
    assert same_proposal is not None
    assert same_proposal.id == proposal.id


async def test_effectiveness_report_aggregates_path_scoped_evidence(db_session):
    user_id, path_id, version_id, node_ids = await _learning_context(db_session)
    now = datetime.now(UTC)
    db_session.add(
        LearningProgress(
            user_id=user_id,
            path_id=path_id,
            node_id=node_ids[0],
            status="completed",
            mastery=82,
            attempts=1,
            completed_at=now,
        )
    )
    db_session.add_all(
        [
            LearningEvent(
                user_id=user_id,
                path_id=path_id,
                node_id=node_ids[0],
                event_type="resource_opened",
                resource_type="lecture",
                client_event_id="report-lecture-open",
                event_metadata={},
                occurred_at=now,
            ),
            LearningEvent(
                user_id=user_id,
                path_id=path_id,
                node_id=node_ids[0],
                event_type="resource_completed",
                resource_type="lecture",
                duration_seconds=125,
                client_event_id="report-lecture-complete",
                event_metadata={},
                occurred_at=now,
            ),
        ]
    )
    assessment_id = str(uuid.uuid4())
    attempt_id = str(uuid.uuid4())
    db_session.add(
        Assessment(
            id=assessment_id,
            user_id=user_id,
            path_id=path_id,
            path_version_id=version_id,
            node_id=node_ids[0],
            purpose="formal",
            status="ready",
        )
    )
    await db_session.flush()
    db_session.add(
        AssessmentAttempt(
            id=attempt_id,
            assessment_id=assessment_id,
            user_id=user_id,
            status="completed",
            score=88,
            passed=True,
            assessment_passed=True,
            finalized_at=now,
        )
    )
    db_session.add(
        MasterySnapshot(
            user_id=user_id,
            node_id=node_ids[0],
            old_mastery=0,
            new_mastery=82,
            evidence="Assessment score: 88%",
            source_type="assessment_attempt",
            source_id=attempt_id,
        )
    )
    db_session.add(
        LearningPathAdaptationProposal(
            user_id=user_id,
            path_id=path_id,
            trigger_node_id=node_ids[0],
            status="dismissed",
            reason="测试适配依据",
            evidence={"trigger": "test"},
            proposed_changes=[],
            decided_at=now,
        )
    )
    await apply_profile_evidence(
        db_session,
        user_id=user_id,
        evidence=[
            ProfileEvidenceInput(
                dimension="concept_grasp",
                value=0.82,
                confidence=0.8,
                evidence_type="assessment_attempt",
                evidence_id=attempt_id,
                evidence_text="正式评估得分 88%",
            )
        ],
    )
    await db_session.commit()

    report = await get_learning_effectiveness(db_session, user_id=user_id, path_id=path_id)
    assert report["overview"]["completion_rate"] == 50.0
    assert report["overview"]["learning_minutes"] == 2.1
    assert report["overview"]["assessment_pass_rate"] == 100.0
    assert report["overview"]["average_score"] == 88.0
    assert report["resource_usage"] == [{"resource_type": "lecture", "opens": 1, "duration_minutes": 2.1}]
    assert report["mastery_trend"][0]["mastery"] == 82
    assert report["profile"]["recent_evidence"][0]["evidence_text"] == "正式评估得分 88%"
    assert report["adaptation"]["proposal_count"] == 1
    assert report["adaptation"]["latest_reason"] == "测试适配依据"


async def test_helpful_tutor_feedback_updates_resource_preference(db_session):
    user_id, path_id, _version_id, node_ids = await _learning_context(db_session)
    _event, profile_version, created = await record_learning_event(
        db_session,
        user_id=user_id,
        path_id=path_id,
        node_id=node_ids[0],
        event_type="tutor_feedback",
        resource_type=None,
        duration_seconds=None,
        client_event_id="helpful-rich-tutor",
        event_metadata={
            "helpful": True,
            "response_modes": ["diagram", "code", "storyboard"],
        },
        occurred_at=datetime.now(UTC),
    )
    await db_session.commit()

    assert created is True
    assert profile_version == 1
    report = await get_learning_effectiveness(db_session, user_id=user_id, path_id=path_id)
    evidence = report["profile"]["recent_evidence"][0]
    assert evidence["dimension"] == "resource_preference"
    assert evidence["evidence_text"] == "Helpful tutor modalities: diagram, code, storyboard"
