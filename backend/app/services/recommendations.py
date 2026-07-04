"""Rule-based recommendation service.

Generates personalized learning recommendations based on:
  1. Review — nodes with mastery < 60% or failed assessments
  2. Practice — available (unlocked) nodes not yet completed
  3. Continue — the earliest available node to continue learning
  4. Resource — knowledge base search hits matching node titles

No LLM is used — this is a pure rule-based engine.

Important: Node status/mastery on LearningNode is the *path-level default*
(stored at generation time). The *runtime* status/mastery lives in
LearningProgress. This service overlays LearningProgress on top of
LearningNode so recommendations reflect actual user state.

Phase 3.6-D: Recommendations are now personalised using the StudentProfile.
Each recommendation's ``reason`` field incorporates profile dimensions
(learning_pace, knowledge_depth, error_pattern, practice_ability,
resource_preference) to provide explainable, learner-specific guidance.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.path import LearningNode, LearningPath
from app.models.profile import StudentProfile
from app.models.progress import LearningProgress
from app.services.knowledge import KnowledgeService

logger = structlog.get_logger()

# Thresholds
MASTERY_REVIEW_THRESHOLD = 60.0
MAX_RECOMMENDATIONS = 10


class RecommendationService:
    """Rule-based recommendation engine."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_recommendations(
        self,
        path_id: str,
        user_id: str,
    ) -> list[dict[str, Any]]:
        """Generate recommendations for a learning path.

        Args:
            path_id: The learning path ID
            user_id: The user ID (for ownership check and knowledge search)

        Returns:
            List of recommendation dicts, ordered by priority:
            continue > review > practice > resource
        """
        # Verify path ownership and get active version
        path = await self._get_path(path_id, user_id)
        if not path or not path.active_version_id:
            return []

        # Get all nodes for the active version
        nodes = await self._get_nodes(path.active_version_id)
        if not nodes:
            return []

        # Overlay LearningProgress on top of LearningNode defaults
        progress_map = await self._get_progress_map(user_id, path_id, nodes)
        effective_nodes = self._merge_node_and_progress(nodes, progress_map)

        # Load student profile for explainable recommendations (Phase 3.6-D)
        profile = await self._load_profile(user_id)

        recommendations: list[dict[str, Any]] = []

        # 1. Continue recommendation — earliest available node
        continue_rec = self._generate_continue_recommendation(effective_nodes, profile)
        if continue_rec:
            recommendations.append(continue_rec)

        # 2. Review recommendations — low mastery or failed
        review_recs = self._generate_review_recommendations(effective_nodes, profile)
        recommendations.extend(review_recs)

        # 3. Practice recommendations — available but not completed
        practice_recs = self._generate_practice_recommendations(effective_nodes, profile)
        recommendations.extend(practice_recs)

        # 4. Resource recommendations — knowledge search hits
        resource_recs = await self._generate_resource_recommendations(user_id, effective_nodes, profile)
        recommendations.extend(resource_recs)

        # Limit total recommendations
        return recommendations[:MAX_RECOMMENDATIONS]

    async def _get_path(self, path_id: str, user_id: str) -> LearningPath | None:
        """Get a learning path, verifying ownership."""
        result = await self.db.execute(
            select(LearningPath).where(
                LearningPath.id == path_id,
                LearningPath.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def _get_nodes(self, version_id: str) -> list[LearningNode]:
        """Get all nodes for a path version, ordered by node_order."""
        result = await self.db.execute(
            select(LearningNode).where(LearningNode.version_id == version_id).order_by(LearningNode.node_order)
        )
        return list(result.scalars().all())

    async def _get_progress_map(
        self,
        user_id: str,
        path_id: str,
        nodes: list[LearningNode],
    ) -> dict[str, LearningProgress]:
        """Fetch LearningProgress for all nodes in a single query.

        Returns a map of node_id → LearningProgress.
        """
        node_ids = [n.id for n in nodes]
        if not node_ids:
            return {}

        result = await self.db.execute(
            select(LearningProgress).where(
                LearningProgress.user_id == user_id,
                LearningProgress.path_id == path_id,
                LearningProgress.node_id.in_(node_ids),
            )
        )
        progress_list = list(result.scalars().all())
        return {p.node_id: p for p in progress_list}

    async def _load_profile(self, user_id: str) -> StudentProfile | None:
        """Load the student profile for personalised recommendation reasons."""
        result = await self.db.execute(select(StudentProfile).where(StudentProfile.user_id == user_id))
        return result.scalar_one_or_none()

    def _merge_node_and_progress(
        self,
        nodes: list[LearningNode],
        progress_map: dict[str, LearningProgress],
    ) -> list[dict[str, Any]]:
        """Merge LearningNode defaults with LearningProgress overrides.

        For each node, the effective status/mastery is:
          - LearningProgress values if a progress row exists
          - LearningNode defaults otherwise

        This ensures recommendations reflect actual user runtime state
        (updated by AssessmentFinalizer), not just the path template.
        """
        effective: list[dict[str, Any]] = []
        for node in nodes:
            progress = progress_map.get(node.id)
            effective.append(
                {
                    "id": node.id,
                    "title": node.title,
                    "description": node.description,
                    "node_order": node.node_order,
                    "difficulty": node.difficulty,
                    "estimated_minutes": node.estimated_minutes,
                    "status": progress.status if progress else node.status,
                    "mastery": progress.mastery if progress else node.mastery,
                }
            )
        return effective

    def _generate_continue_recommendation(
        self,
        nodes: list[dict[str, Any]],
        profile: StudentProfile | None = None,
    ) -> dict[str, Any] | None:
        """Generate a 'continue learning' recommendation.

        Finds the earliest available (unlocked) node that is not yet completed.
        """
        for node in nodes:
            if node["status"] == "available" and node["mastery"] < 100.0:
                # Build personalised reason from profile (Phase 3.6-D)
                reason = f"这是你当前可以学习的下一个节点，预计需要 {node['estimated_minutes']} 分钟。"
                if profile and profile.dimensions:
                    pace = profile.dimensions.get("learning_pace", {})
                    pace_value = pace.get("value") if pace else None
                    if pace_value == "fast":
                        reason += "根据你的学习节奏，可以适当加快进度。"
                    elif pace_value == "slow":
                        reason += "根据你的学习节奏，建议稳扎稳打，不必赶进度。"

                    kd = profile.dimensions.get("knowledge_depth", {})
                    kd_value = kd.get("value") if kd else None
                    if isinstance(kd_value, (int, float)) and kd_value > 0.7:
                        reason += "你的知识基础较好，可以重点关注进阶内容。"
                    elif isinstance(kd_value, (int, float)) and kd_value < 0.3:
                        reason += "建议先夯实基础概念，再逐步深入。"

                return {
                    "id": str(uuid.uuid4()),
                    "type": "continue",
                    "title": f"继续学习：{node['title']}",
                    "reason": reason,
                    "node_ids": [node["id"]],
                    "status": "new",
                    "resource": None,
                }
        return None

    def _generate_review_recommendations(
        self,
        nodes: list[dict[str, Any]],
        profile: StudentProfile | None = None,
    ) -> list[dict[str, Any]]:
        """Generate review recommendations for low-mastery nodes.

        A node gets a review recommendation if:
          - mastery < 60% and status is 'completed', OR
          - status is 'failed'

        When a profile is available, the reason is enriched with error-pattern
        and concept-grasp information (Phase 3.6-D).
        """
        recommendations: list[dict[str, Any]] = []

        # Extract error patterns from profile for personalised reasons
        error_patterns: dict[str, float] = {}
        concept_grasp: float | None = None
        if profile and profile.dimensions:
            ep = profile.dimensions.get("error_pattern", {})
            ep_value = ep.get("value") if ep else None
            if isinstance(ep_value, dict):
                error_patterns = ep_value
            cg = profile.dimensions.get("concept_grasp", {})
            cg_value = cg.get("value") if cg else None
            if isinstance(cg_value, (int, float)):
                concept_grasp = cg_value

        for node in nodes:
            needs_review = False
            reason = ""

            if node["status"] == "completed" and node["mastery"] < MASTERY_REVIEW_THRESHOLD:
                needs_review = True
                reason = (
                    f"该节点掌握度为 {node['mastery']:.0f}%，低于推荐阈值 "
                    f"{MASTERY_REVIEW_THRESHOLD:.0f}%，建议复习巩固。"
                )
            elif node["status"] == "failed":
                needs_review = True
                reason = "该节点评估未通过，建议复习后重新尝试。"

            if needs_review:
                # Enrich reason with profile data (Phase 3.6-D)
                if concept_grasp is not None and concept_grasp < 0.5:
                    reason += "你的概念理解能力还有提升空间，复习时建议重点关注核心概念。"
                if error_patterns:
                    top_errors = sorted(error_patterns.items(), key=lambda x: x[1], reverse=True)[:2]
                    error_names = [k for k, _ in top_errors]
                    if error_names:
                        reason += f"常见薄弱点：{'、'.join(error_names)}。"

                recommendations.append(
                    {
                        "id": str(uuid.uuid4()),
                        "type": "review",
                        "title": f"复习：{node['title']}",
                        "reason": reason,
                        "node_ids": [node["id"]],
                        "status": "new",
                        "resource": None,
                    }
                )

        return recommendations

    def _generate_practice_recommendations(
        self,
        nodes: list[dict[str, Any]],
        profile: StudentProfile | None = None,
    ) -> list[dict[str, Any]]:
        """Generate practice recommendations for available nodes.

        Nodes that are 'available' (unlocked) but not yet completed
        get a practice recommendation. When a profile is available, the
        reason references the learner's practice_ability and resource
        preferences (Phase 3.6-D).
        """
        recommendations: list[dict[str, Any]] = []

        # Extract practice ability and resource preferences from profile
        practice_ability: float | None = None
        resource_prefs: list[str] = []
        if profile and profile.dimensions:
            pa = profile.dimensions.get("practice_ability", {})
            pa_value = pa.get("value") if pa else None
            if isinstance(pa_value, (int, float)):
                practice_ability = pa_value
            rp = profile.dimensions.get("resource_preference", {})
            rp_value = rp.get("value") if rp else None
            if isinstance(rp_value, list):
                resource_prefs = [str(v) for v in rp_value]

        for node in nodes:
            if node["status"] == "available" and node["mastery"] < 100.0:
                reason = f"该节点已解锁，难度为 {node['difficulty']}，建议通过练习加深理解。"

                # Personalise reason (Phase 3.6-D)
                if practice_ability is not None and practice_ability < 0.4:
                    reason += "你的动手实践能力还有提升空间，多做练习会有显著进步。"
                if "quiz" in resource_prefs:
                    reason += "你偏好通过刷题学习，可以先用题库练习。"
                elif "project" in resource_prefs:
                    reason += "你偏好项目实战，可以尝试用该知识点完成一个小项目。"

                recommendations.append(
                    {
                        "id": str(uuid.uuid4()),
                        "type": "practice",
                        "title": f"练习：{node['title']}",
                        "reason": reason,
                        "node_ids": [node["id"]],
                        "status": "new",
                        "resource": None,
                    }
                )

        return recommendations

    async def _generate_resource_recommendations(
        self,
        user_id: str,
        nodes: list[dict[str, Any]],
        profile: StudentProfile | None = None,
    ) -> list[dict[str, Any]]:
        """Generate resource recommendations from knowledge base.

        Searches the user's knowledge base for content matching
        node titles. If matches are found, creates resource recommendations.
        """
        recommendations: list[dict[str, Any]] = []
        service = KnowledgeService(self.db)

        # Extract resource preferences from profile for personalised reasons
        resource_prefs: list[str] = []
        if profile and profile.dimensions:
            rp = profile.dimensions.get("resource_preference", {})
            rp_value = rp.get("value") if rp else None
            if isinstance(rp_value, list):
                resource_prefs = [str(v) for v in rp_value]

        # Search for each node title (limit to first 5 nodes to avoid too many queries)
        for node in nodes[:5]:
            if not node["title"]:
                continue

            try:
                results = await service.search(
                    user_id=user_id,
                    query=node["title"],
                    limit=1,
                )
            except Exception as e:
                logger.warning(
                    "resource_search_failed",
                    node_id=node["id"],
                    error=str(e),
                )
                continue

            if results:
                top_result = results[0]
                reason = (
                    f"知识库中找到与「{node['title']}」相关的内容"
                    + (f"（来源：{top_result['file_name']}）" if top_result.get("file_name") else "")
                    + "，建议参考学习。"
                )
                # Personalise reason with resource preferences (Phase 3.6-D)
                if "reading" in resource_prefs:
                    reason += "你喜欢通过阅读学习，这份资料很适合你。"
                elif "video" in resource_prefs:
                    reason += "如果文档中有视频链接，建议优先观看。"

                recommendations.append(
                    {
                        "id": str(uuid.uuid4()),
                        "type": "resource",
                        "title": f"补充资料：{node['title']}",
                        "reason": reason,
                        "node_ids": [node["id"]],
                        "status": "new",
                        "resource": {
                            "document_id": top_result.get("document_id"),
                            "file_name": top_result.get("file_name"),
                            "chunk_id": top_result.get("id"),
                            "page_number": top_result.get("page_number"),
                            "section_title": top_result.get("section_title"),
                        },
                    }
                )

        return recommendations
