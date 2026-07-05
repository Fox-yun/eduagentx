"""Dynamic recommendation service.

Generates personalized learning recommendations based on:
  1. Continue — the earliest available node to continue learning
  2. Review — nodes with mastery < 60% or failed assessments
  3. Review Weak Point — error_pattern from profile triggers targeted review
  4. Practice — available (unlocked) nodes not yet completed
  5. Resource — knowledge base search hits matching node titles
  6. Ask Tutor — low concept_grasp suggests asking the tutor
  7. Revise Path — consecutive assessment failures suggest path revision

No LLM is used — this is a pure rule-based engine enhanced with profile data.

Phase 3.8: Upgraded from static recommendations to dynamic recommendations
with evidence, priority, confidence, and action fields. Each recommendation
now includes explainable evidence and a clear next-step action.

Important: Node status/mastery on LearningNode is the *path-level default*
(stored at generation time). The *runtime* status/mastery lives in
LearningProgress. This service overlays LearningProgress on top of
LearningNode so recommendations reflect actual user state.
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
from app.models.unit import AssessmentAttempt
from app.services.knowledge import KnowledgeService

logger = structlog.get_logger()

# Thresholds
MASTERY_REVIEW_THRESHOLD = 60.0
MAX_RECOMMENDATIONS = 10
CONSECUTIVE_FAILURE_THRESHOLD = 2  # 2+ failed attempts → suggest path revision
LOW_CONCEPT_GRASP_THRESHOLD = 0.4  # concept_grasp < 0.4 → suggest tutor

# Priority levels (higher = more important)
PRIORITY_HIGH = 3
PRIORITY_MEDIUM = 2
PRIORITY_LOW = 1


class RecommendationService:
    """Dynamic recommendation engine with profile-aware rules."""

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
            revise_path > review > review_weak_point > continue > practice > ask_tutor > resource
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

        # Load student profile for explainable recommendations
        profile = await self._load_profile(user_id)

        # Check for consecutive assessment failures
        failed_node_ids = await self._get_consecutive_failure_nodes(user_id, path_id)

        recommendations: list[dict[str, Any]] = []

        # 1. Revise path recommendation — consecutive failures
        if failed_node_ids:
            revise_rec = self._generate_revise_path_recommendation(effective_nodes, failed_node_ids, profile)
            if revise_rec:
                recommendations.append(revise_rec)

        # 2. Review recommendations — low mastery or failed
        review_recs = self._generate_review_recommendations(effective_nodes, profile)
        recommendations.extend(review_recs)

        # 3. Review weak point — error_pattern targeted
        weak_point_recs = self._generate_review_weak_point_recommendations(effective_nodes, profile)
        recommendations.extend(weak_point_recs)

        # 4. Continue recommendation — earliest available node
        continue_rec = self._generate_continue_recommendation(effective_nodes, profile)
        if continue_rec:
            recommendations.append(continue_rec)

        # 5. Practice recommendations — available but not completed
        practice_recs = self._generate_practice_recommendations(effective_nodes, profile)
        recommendations.extend(practice_recs)

        # 6. Ask tutor recommendation — low concept_grasp
        tutor_rec = self._generate_ask_tutor_recommendation(effective_nodes, profile)
        if tutor_rec:
            recommendations.append(tutor_rec)

        # 7. Resource recommendations — knowledge search hits
        resource_recs = await self._generate_resource_recommendations(user_id, effective_nodes, profile)
        recommendations.extend(resource_recs)

        # Sort by priority (descending) then limit
        recommendations.sort(key=lambda r: r.get("priority", PRIORITY_LOW), reverse=True)
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
        """Fetch LearningProgress for all nodes in a single query."""
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

    async def _get_consecutive_failure_nodes(
        self,
        user_id: str,
        path_id: str,
    ) -> list[str]:
        """Detect nodes with consecutive assessment failures.

        Returns a list of node_ids where the user has 2+ failed attempts
        on the most recent assessments.
        """
        result = await self.db.execute(
            select(
                AssessmentAttempt.user_id,
                AssessmentAttempt.assessment_id,
            )
            .where(
                AssessmentAttempt.user_id == user_id,
                AssessmentAttempt.passed == False,  # noqa: E712
                AssessmentAttempt.status == "completed",
            )
            .order_by(AssessmentAttempt.submitted_at.desc())
            .limit(20)
        )
        rows = result.all()
        if not rows:
            return []

        # Count failures per assessment_id
        failure_counts: dict[str, int] = {}
        for row in rows:
            assessment_id = row[1]
            failure_counts[assessment_id] = failure_counts.get(assessment_id, 0) + 1

        # Return assessment_ids with 2+ failures
        return [aid for aid, count in failure_counts.items() if count >= CONSECUTIVE_FAILURE_THRESHOLD]

    def _merge_node_and_progress(
        self,
        nodes: list[LearningNode],
        progress_map: dict[str, LearningProgress],
    ) -> list[dict[str, Any]]:
        """Merge LearningNode defaults with LearningProgress overrides."""
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

    # ---- Recommendation generators ----

    def _generate_continue_recommendation(
        self,
        nodes: list[dict[str, Any]],
        profile: StudentProfile | None = None,
    ) -> dict[str, Any] | None:
        """Generate a 'continue learning' recommendation."""
        for node in nodes:
            if node["status"] == "available" and node["mastery"] < 100.0:
                reason = f"这是你当前可以学习的下一个节点，预计需要 {node['estimated_minutes']} 分钟。"
                evidence_parts: list[str] = ["节点状态: available"]
                confidence = 0.9
                action = "open_node"

                if profile and profile.dimensions:
                    pace = profile.dimensions.get("learning_pace", {})
                    pace_value = pace.get("value") if pace else None
                    if pace_value == "fast":
                        reason += "根据你的学习节奏，可以适当加快进度。"
                        evidence_parts.append("学习节奏: fast")
                    elif pace_value == "slow":
                        reason += "根据你的学习节奏，建议稳扎稳打，不必赶进度。"
                        evidence_parts.append("学习节奏: slow")

                    kd = profile.dimensions.get("knowledge_depth", {})
                    kd_value = kd.get("value") if kd else None
                    if isinstance(kd_value, (int, float)) and kd_value > 0.7:
                        reason += "你的知识基础较好，可以重点关注进阶内容。"
                        evidence_parts.append(f"知识深度: {kd_value:.1f}")
                    elif isinstance(kd_value, (int, float)) and kd_value < 0.3:
                        reason += "建议先夯实基础概念，再逐步深入。"
                        evidence_parts.append(f"知识深度: {kd_value:.1f}")

                return {
                    "id": str(uuid.uuid4()),
                    "type": "continue",
                    "title": f"继续学习：{node['title']}",
                    "reason": reason,
                    "node_ids": [node["id"]],
                    "status": "new",
                    "resource": None,
                    "evidence": evidence_parts,
                    "priority": PRIORITY_MEDIUM,
                    "confidence": confidence,
                    "action": action,
                }
        return None

    def _generate_review_recommendations(
        self,
        nodes: list[dict[str, Any]],
        profile: StudentProfile | None = None,
    ) -> list[dict[str, Any]]:
        """Generate review recommendations for low-mastery nodes."""
        recommendations: list[dict[str, Any]] = []

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
            evidence_parts: list[str] = []

            if node["status"] == "completed" and node["mastery"] < MASTERY_REVIEW_THRESHOLD:
                needs_review = True
                reason = (
                    f"该节点掌握度为 {node['mastery']:.0f}%，低于推荐阈值 "
                    f"{MASTERY_REVIEW_THRESHOLD:.0f}%，建议复习巩固。"
                )
                evidence_parts.append(f"掌握度: {node['mastery']:.0f}%")
            elif node["status"] == "failed":
                needs_review = True
                reason = "该节点评估未通过，建议复习后重新尝试。"
                evidence_parts.append("评估状态: failed")

            if needs_review:
                if concept_grasp is not None and concept_grasp < 0.5:
                    reason += "你的概念理解能力还有提升空间，复习时建议重点关注核心概念。"
                    evidence_parts.append(f"概念理解: {concept_grasp:.1f}")
                if error_patterns:
                    top_errors = sorted(error_patterns.items(), key=lambda x: x[1], reverse=True)[:2]
                    error_names = [k for k, _ in top_errors]
                    if error_names:
                        reason += f"常见薄弱点：{'、'.join(error_names)}。"
                        evidence_parts.append(f"错误模式: {', '.join(error_names)}")

                recommendations.append(
                    {
                        "id": str(uuid.uuid4()),
                        "type": "review",
                        "title": f"复习：{node['title']}",
                        "reason": reason,
                        "node_ids": [node["id"]],
                        "status": "new",
                        "resource": None,
                        "evidence": evidence_parts,
                        "priority": PRIORITY_HIGH,
                        "confidence": 0.85,
                        "action": "review_node",
                    }
                )

        return recommendations

    def _generate_review_weak_point_recommendations(
        self,
        nodes: list[dict[str, Any]],
        profile: StudentProfile | None = None,
    ) -> list[dict[str, Any]]:
        """Generate targeted review recommendations based on error patterns.

        When the profile has error_pattern data, create a targeted
        review recommendation that suggests practicing specific weak points.
        """
        if not profile or not profile.dimensions:
            return []

        ep = profile.dimensions.get("error_pattern", {})
        ep_value = ep.get("value") if ep else None
        if not isinstance(ep_value, dict) or not ep_value:
            return []

        # Find the top error pattern
        top_errors = sorted(ep_value.items(), key=lambda x: x[1], reverse=True)[:3]
        error_names = [k for k, _ in top_errors]

        # Find nodes that might be related to these error patterns
        # (match by title keywords)
        related_nodes: list[str] = []
        for node in nodes:
            title_lower = node["title"].lower() if node["title"] else ""
            for err in error_names:
                if err.lower() in title_lower:
                    related_nodes.append(node["id"])
                    break

        # If no related nodes found, use the first available node
        if not related_nodes:
            for node in nodes:
                if node["status"] in ("available", "completed"):
                    related_nodes.append(node["id"])
                    break

        if not related_nodes:
            return []

        reason = (
            f"根据你的学习画像，你在以下方面存在薄弱点：{'、'.join(error_names)}。"
            "建议针对性地复习相关知识点并完成变式练习。"
        )
        evidence_parts = [f"错误模式命中: {', '.join(error_names)}"]

        return [
            {
                "id": str(uuid.uuid4()),
                "type": "review_weak_point",
                "title": f"针对性复习：{'、'.join(error_names)}",
                "reason": reason,
                "node_ids": related_nodes[:3],
                "status": "new",
                "resource": None,
                "evidence": evidence_parts,
                "priority": PRIORITY_HIGH,
                "confidence": 0.8,
                "action": "practice_weak_point",
            }
        ]

    def _generate_practice_recommendations(
        self,
        nodes: list[dict[str, Any]],
        profile: StudentProfile | None = None,
    ) -> list[dict[str, Any]]:
        """Generate practice recommendations for available nodes."""
        recommendations: list[dict[str, Any]] = []

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
                evidence_parts: list[str] = [f"难度: {node['difficulty']}"]

                if practice_ability is not None and practice_ability < 0.4:
                    reason += "你的动手实践能力还有提升空间，多做练习会有显著进步。"
                    evidence_parts.append(f"实践能力: {practice_ability:.1f}")
                if "quiz" in resource_prefs:
                    reason += "你偏好通过刷题学习，可以先用题库练习。"
                    evidence_parts.append("偏好: quiz")
                elif "project" in resource_prefs:
                    reason += "你偏好项目实战，可以尝试用该知识点完成一个小项目。"
                    evidence_parts.append("偏好: project")
                elif "mind_map" in resource_prefs:
                    reason += "你偏好思维导图学习，建议先生成思维导图梳理知识结构。"
                    evidence_parts.append("偏好: mind_map")

                recommendations.append(
                    {
                        "id": str(uuid.uuid4()),
                        "type": "practice",
                        "title": f"练习：{node['title']}",
                        "reason": reason,
                        "node_ids": [node["id"]],
                        "status": "new",
                        "resource": None,
                        "evidence": evidence_parts,
                        "priority": PRIORITY_LOW,
                        "confidence": 0.7,
                        "action": "start_practice",
                    }
                )

        return recommendations

    def _generate_ask_tutor_recommendation(
        self,
        nodes: list[dict[str, Any]],
        profile: StudentProfile | None = None,
    ) -> dict[str, Any] | None:
        """Generate an 'ask tutor' recommendation when concept_grasp is low."""
        if not profile or not profile.dimensions:
            return None

        cg = profile.dimensions.get("concept_grasp", {})
        cg_value = cg.get("value") if cg else None
        if not isinstance(cg_value, (int, float)) or cg_value >= LOW_CONCEPT_GRASP_THRESHOLD:
            return None

        # Find a relevant node (first available or in-progress)
        target_node_id: str | None = None
        target_title = "当前节点"
        for node in nodes:
            if node["status"] in ("available", "completed", "in_progress"):
                target_node_id = node["id"]
                target_title = node["title"]
                break

        if not target_node_id:
            return None

        reason = f"你的概念理解能力评分为 {cg_value:.1f}，建议向 Tutor 提问以加深对「{target_title}」核心概念的理解。"
        evidence_parts = [f"概念理解: {cg_value:.1f}", f"阈值: < {LOW_CONCEPT_GRASP_THRESHOLD}"]

        return {
            "id": str(uuid.uuid4()),
            "type": "ask_tutor",
            "title": f"向 Tutor 提问：{target_title}",
            "reason": reason,
            "node_ids": [target_node_id] if target_node_id else [],
            "status": "new",
            "resource": None,
            "evidence": evidence_parts,
            "priority": PRIORITY_MEDIUM,
            "confidence": 0.75,
            "action": "open_tutor",
        }

    def _generate_revise_path_recommendation(
        self,
        nodes: list[dict[str, Any]],
        failed_node_ids: list[str],
        profile: StudentProfile | None = None,
    ) -> dict[str, Any] | None:
        """Generate a 'revise path' recommendation for consecutive failures."""
        if not failed_node_ids:
            return None

        reason = (
            f"你在最近的学习中连续 {CONSECUTIVE_FAILURE_THRESHOLD} 次或以上评估未通过，"
            "当前学习路径可能不太适合你的水平。建议修订学习路径，调整难度和节奏。"
        )
        evidence_parts = [f"连续失败次数: ≥{CONSECUTIVE_FAILURE_THRESHOLD}"]

        if profile and profile.dimensions:
            kd = profile.dimensions.get("knowledge_depth", {})
            kd_value = kd.get("value") if kd else None
            if isinstance(kd_value, (int, float)) and kd_value < 0.3:
                reason += "你的知识基础较薄弱，修订后的路径应增加基础节点。"
                evidence_parts.append(f"知识深度: {kd_value:.1f}")

        # Find related nodes
        related_nodes = [n["id"] for n in nodes if n["id"] in failed_node_ids][:3]
        if not related_nodes:
            related_nodes = [n["id"] for n in nodes[:3]]

        return {
            "id": str(uuid.uuid4()),
            "type": "revise_path",
            "title": "修订学习路径",
            "reason": reason,
            "node_ids": related_nodes,
            "status": "new",
            "resource": None,
            "evidence": evidence_parts,
            "priority": PRIORITY_HIGH,
            "confidence": 0.9,
            "action": "request_path_revision",
        }

    async def _generate_resource_recommendations(
        self,
        user_id: str,
        nodes: list[dict[str, Any]],
        profile: StudentProfile | None = None,
    ) -> list[dict[str, Any]]:
        """Generate resource recommendations from knowledge base."""
        recommendations: list[dict[str, Any]] = []

        service = KnowledgeService(self.db)

        resource_prefs: list[str] = []
        if profile and profile.dimensions:
            rp = profile.dimensions.get("resource_preference", {})
            rp_value = rp.get("value") if rp else None
            if isinstance(rp_value, list):
                resource_prefs = [str(v) for v in rp_value]

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
                evidence_parts = [f"知识库匹配: {node['title']}"]
                if top_result.get("file_name"):
                    evidence_parts.append(f"文件: {top_result['file_name']}")

                if "reading" in resource_prefs:
                    reason += "你喜欢通过阅读学习，这份资料很适合你。"
                    evidence_parts.append("偏好: reading")
                elif "video" in resource_prefs:
                    reason += "如果文档中有视频链接，建议优先观看。"
                    evidence_parts.append("偏好: video")

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
                        "evidence": evidence_parts,
                        "priority": PRIORITY_LOW,
                        "confidence": 0.6,
                        "action": "read_document",
                    }
                )

        return recommendations
