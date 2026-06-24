"""Unit content and assessment service."""

from __future__ import annotations

import json
import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.datetime import utc_now
from app.core.errors import ApiError
from app.models.path import LearningEdge
from app.models.progress import LearningProgress, MasterySnapshot
from app.models.unit import (
    Assessment,
    AssessmentAnswer,
    AssessmentAttempt,
    AssessmentQuestion,
    LearningUnitContent,
)

logger = structlog.get_logger()

# Pass threshold
PASS_THRESHOLD = 60.0


class UnitService:
    """Unit content and assessment business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_unit_content(
        self,
        path_id: str,
        node_id: str,
        user_id: str,
    ) -> dict[str, object]:
        """Get unit content for a node."""
        result = await self.db.execute(
            select(LearningUnitContent).where(
                LearningUnitContent.path_id == path_id,
                LearningUnitContent.node_id == node_id,
                LearningUnitContent.user_id == user_id,
            )
        )
        content = result.scalar_one_or_none()

        if not content:
            return {
                "unit_id": f"unit-{node_id}",
                "path_id": path_id,
                "path_version": 1,
                "node_id": node_id,
                "content_version": 1,
                "status": "generating",
                "active_task_id": None,
                "introduction": None,
                "objectives": [],
                "sections": [],
                "practice_tasks": [],
                "summary": None,
                "references": [],
                "error": None,
            }

        content_data = content.content or {}
        return {
            "unit_id": content.id,
            "path_id": content.path_id,
            "path_version": 1,
            "node_id": content.node_id,
            "content_version": content.version_number,
            "status": content.status,
            "active_task_id": None,
            "introduction": content_data.get("introduction"),
            "objectives": content_data.get("objectives", []),
            "sections": content_data.get("sections", []),
            "practice_tasks": content_data.get("practice_tasks", []),
            "summary": content_data.get("summary"),
            "references": content_data.get("references", []),
            "error": content_data.get("error"),
        }

    async def create_assessment(
        self,
        path_id: str,
        node_id: str,
        user_id: str,
    ) -> dict[str, object]:
        """Create an assessment for a node."""
        # Check if assessment already exists
        result = await self.db.execute(
            select(Assessment).where(
                Assessment.path_id == path_id,
                Assessment.node_id == node_id,
                Assessment.user_id == user_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return await self._format_assessment(existing)

        # Create assessment
        assessment = Assessment(
            id=str(uuid.uuid4()),
            user_id=user_id,
            path_id=path_id,
            path_version_id="",
            node_id=node_id,
            status="pending",
        )
        self.db.add(assessment)

        # Create sample questions (in production, these would come from LLM)
        questions = [
            AssessmentQuestion(
                id=str(uuid.uuid4()),
                assessment_id=assessment.id,
                question_type="single_choice",
                prompt="本单元的核心概念是什么？",
                options=json.dumps(
                    [
                        {"value": "a", "label": "选项A"},
                        {"value": "b", "label": "选项B"},
                        {"value": "c", "label": "选项C"},
                    ]
                ),
                correct_answer="a",
                points=1,
                question_order=1,
            ),
        ]

        for q in questions:
            self.db.add(q)

        await self.db.flush()
        return await self._format_assessment(assessment)

    async def submit_assessment(
        self,
        assessment_id: str,
        user_id: str,
        answers: dict[str, str | list[str]],
    ) -> dict:
        """Submit an assessment attempt."""
        # Get assessment
        result = await self.db.execute(
            select(Assessment).where(
                Assessment.id == assessment_id,
                Assessment.user_id == user_id,
            )
        )
        assessment = result.scalar_one_or_none()
        if not assessment:
            raise ApiError(code="ASSESSMENT_NOT_FOUND", message="Assessment not found", status_code=404)

        # Get questions
        questions_result = await self.db.execute(
            select(AssessmentQuestion)
            .where(AssessmentQuestion.assessment_id == assessment_id)
            .order_by(AssessmentQuestion.question_order)
        )
        questions = list(questions_result.scalars().all())

        # Create attempt
        attempt = AssessmentAttempt(
            id=str(uuid.uuid4()),
            assessment_id=assessment_id,
            user_id=user_id,
            status="in_progress",
        )
        self.db.add(attempt)

        # Grade answers
        total_points = 0
        earned_points = 0
        weak_concepts: list[str] = []
        explanations: dict[str, str] = {}

        for question in questions:
            total_points += question.points
            answer_value = answers.get(question.id)
            is_correct = False
            points_earned = 0
            feedback = ""

            if answer_value is not None:
                if question.question_type in ("single_choice", "multiple_choice"):
                    correct = question.correct_answer
                    if isinstance(answer_value, list):
                        is_correct = set(answer_value) == set(json.loads(correct) if correct else [])
                    else:
                        is_correct = str(answer_value) == str(correct)

                if is_correct:
                    points_earned = question.points
                    earned_points += question.points
                else:
                    weak_concepts.append(question.prompt[:50])
                    feedback = f"正确答案: {question.correct_answer}"

            # Save answer
            answer = AssessmentAnswer(
                id=str(uuid.uuid4()),
                attempt_id=attempt.id,
                question_id=question.id,
                answer_value=json.dumps(answer_value) if answer_value else None,
                is_correct=is_correct,
                points_earned=points_earned,
                feedback=feedback,
            )
            self.db.add(answer)

        # Calculate score
        score = (earned_points / total_points * 100) if total_points > 0 else 0
        passed = score >= PASS_THRESHOLD

        # Update attempt
        attempt.status = "scored"
        attempt.score = score
        attempt.passed = passed
        attempt.feedback = "恭喜通过！" if passed else "未通过，建议重新学习"
        attempt.weak_concepts = weak_concepts
        attempt.explanations = explanations
        attempt.submitted_at = utc_now()

        # Update assessment status
        assessment.status = "submitted"

        # Update mastery and progress
        await self._update_mastery(user_id, assessment.node_id, score, passed, assessment_id)
        await self._update_progress(user_id, assessment.path_id, assessment.node_id, passed)

        await self.db.flush()

        return {
            "score": score,
            "passed": passed,
            "feedback": attempt.feedback,
            "mastery_delta": score - 50 if passed else 0,
            "weak_concepts": weak_concepts,
            "explanations": explanations,
            "recommended_actions": ["重新学习本单元"] if not passed else [],
        }

    async def _update_mastery(
        self,
        user_id: str,
        node_id: str,
        score: float,
        passed: bool,
        source_id: str,
    ) -> None:
        """Update mastery based on assessment result."""
        # Get current progress
        result = await self.db.execute(
            select(LearningProgress).where(
                LearningProgress.user_id == user_id,
                LearningProgress.node_id == node_id,
            )
        )
        progress = result.scalar_one_or_none()

        old_mastery = progress.mastery if progress else 0.0
        new_mastery = min(100.0, old_mastery + (score - 50) * 0.5) if passed else old_mastery

        # Create mastery snapshot
        snapshot = MasterySnapshot(
            id=str(uuid.uuid4()),
            user_id=user_id,
            node_id=node_id,
            old_mastery=old_mastery,
            new_mastery=new_mastery,
            evidence=f"Assessment score: {score}",
            source_type="assessment",
            source_id=source_id,
        )
        self.db.add(snapshot)

    async def _update_progress(
        self,
        user_id: str,
        path_id: str,
        node_id: str,
        passed: bool,
    ) -> None:
        """Update learning progress and unlock next nodes."""
        # Get or create progress
        result = await self.db.execute(
            select(LearningProgress).where(
                LearningProgress.user_id == user_id,
                LearningProgress.path_id == path_id,
                LearningProgress.node_id == node_id,
            )
        )
        progress = result.scalar_one_or_none()

        if not progress:
            progress = LearningProgress(
                id=str(uuid.uuid4()),
                user_id=user_id,
                path_id=path_id,
                node_id=node_id,
                status="in_progress",
            )
            self.db.add(progress)

        progress.attempts += 1

        if passed:
            progress.status = "completed"
            progress.completed_at = utc_now()

            # Unlock next nodes
            await self._unlock_next_nodes(user_id, path_id, node_id)

    async def _unlock_next_nodes(
        self,
        user_id: str,
        path_id: str,
        completed_node_id: str,
    ) -> None:
        """Unlock nodes whose prerequisites are all completed."""
        # Get edges where completed node is source
        edges_result = await self.db.execute(
            select(LearningEdge).where(LearningEdge.source_node_id == completed_node_id)
        )
        outgoing_edges = list(edges_result.scalars().all())

        for edge in outgoing_edges:
            target_node_id = edge.target_node_id

            # Check all prerequisites of target node
            prereq_result = await self.db.execute(
                select(LearningEdge).where(LearningEdge.target_node_id == target_node_id)
            )
            prereq_edges = list(prereq_result.scalars().all())

            all_prereqs_met = True
            for prereq_edge in prereq_edges:
                prereq_progress = await self.db.execute(
                    select(LearningProgress).where(
                        LearningProgress.user_id == user_id,
                        LearningProgress.path_id == path_id,
                        LearningProgress.node_id == prereq_edge.source_node_id,
                    )
                )
                prereq = prereq_progress.scalar_one_or_none()
                if not prereq or prereq.status != "completed":
                    all_prereqs_met = False
                    break

            if all_prereqs_met:
                # Unlock target node
                target_progress = await self.db.execute(
                    select(LearningProgress).where(
                        LearningProgress.user_id == user_id,
                        LearningProgress.path_id == path_id,
                        LearningProgress.node_id == target_node_id,
                    )
                )
                progress = target_progress.scalar_one_or_none()
                if progress and progress.status == "locked":
                    progress.status = "available"
                elif not progress:
                    progress = LearningProgress(
                        id=str(uuid.uuid4()),
                        user_id=user_id,
                        path_id=path_id,
                        node_id=target_node_id,
                        status="available",
                    )
                    self.db.add(progress)

    async def _format_assessment(self, assessment: Assessment) -> dict:
        """Format assessment for API response."""
        questions_result = await self.db.execute(
            select(AssessmentQuestion)
            .where(AssessmentQuestion.assessment_id == assessment.id)
            .order_by(AssessmentQuestion.question_order)
        )
        questions = list(questions_result.scalars().all())

        return {
            "assessment_id": assessment.id,
            "path_id": assessment.path_id,
            "path_version": 1,
            "node_id": assessment.node_id,
            "status": assessment.status,
            "questions": [
                {
                    "question_id": q.id,
                    "type": q.question_type,
                    "prompt": q.prompt,
                    "options": q.options if q.options else [],
                }
                for q in questions
            ],
            "saved_answers": {},
            "score": None,
            "mastery": None,
            "passed": None,
            "weak_concepts": [],
            "explanations": {},
            "recommended_actions": [],
        }
