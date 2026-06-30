"""Learning path service."""

from __future__ import annotations

import json
import uuid

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.datetime import to_iso_string, utc_now
from app.core.errors import ApiError
from app.models.goal import LearningGoal
from app.models.path import (
    LearningEdge,
    LearningNode,
    LearningPath,
    LearningPathRevisionRequest,
    LearningPathVersion,
    LearningStage,
    validate_dag,
)
from app.models.progress import LearningProgress

logger = structlog.get_logger()


class PathService:
    """Learning path business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_path(self, path_id: str, user_id: str) -> LearningPath:
        """Get a path by ID, ensuring ownership."""
        result = await self.db.execute(
            select(LearningPath).where(
                LearningPath.id == path_id,
                LearningPath.user_id == user_id,
            )
        )
        path = result.scalar_one_or_none()
        if not path:
            raise ApiError(code="PATH_NOT_FOUND", message="Learning path not found", status_code=404)
        return path

    async def get_path_with_details(self, path_id: str, user_id: str) -> dict:
        """Get a path with all its versions, stages, nodes, and edges."""
        path = await self.get_path(path_id, user_id)

        # Get active version or latest draft
        version_query = select(LearningPathVersion).where(LearningPathVersion.path_id == path_id)
        if path.active_version_id:
            version_query = version_query.where(LearningPathVersion.id == path.active_version_id)
        else:
            version_query = version_query.order_by(LearningPathVersion.version_number.desc()).limit(1)

        result = await self.db.execute(version_query)
        version = result.scalar_one_or_none()

        if not version:
            return await self._format_path(path, None, [], [], [])

        # Get stages
        stages_result = await self.db.execute(
            select(LearningStage).where(LearningStage.version_id == version.id).order_by(LearningStage.stage_order)
        )
        stages = list(stages_result.scalars().all())

        # Get nodes
        nodes_result = await self.db.execute(
            select(LearningNode).where(LearningNode.version_id == version.id).order_by(LearningNode.node_order)
        )
        nodes = list(nodes_result.scalars().all())

        # Get edges
        edges_result = await self.db.execute(select(LearningEdge).where(LearningEdge.version_id == version.id))
        edges = list(edges_result.scalars().all())

        return await self._format_path(path, version, stages, nodes, edges)

    async def create_path_version(
        self,
        path_id: str,
        user_id: str,
        stages: list[dict],
        nodes: list[dict],
        edges: list[dict],
        source: str = "initial_generation",
        summary: str | None = None,
    ) -> LearningPathVersion:
        """Create a new version of a learning path with DAG validation."""
        await self.get_path(path_id, user_id)

        # Validate DAG
        validate_dag(nodes, edges)

        # Get next version number
        result = await self.db.execute(
            select(LearningPathVersion.version_number)
            .where(LearningPathVersion.path_id == path_id)
            .order_by(LearningPathVersion.version_number.desc())
            .limit(1)
        )
        last_version = result.scalar()
        next_version = (last_version or 0) + 1

        # Calculate total time
        total_minutes = sum(n.get("estimated_minutes", 30) for n in nodes)

        # Create version
        version = LearningPathVersion(
            id=str(uuid.uuid4()),
            path_id=path_id,
            version_number=next_version,
            source=source,
            status="draft",
            summary=summary,
            estimated_total_minutes=total_minutes,
        )
        self.db.add(version)

        # Flush version before creating child records (FK constraint)
        await self.db.flush()

        # Create stages
        stage_id_map = {}
        for stage_data in stages:
            stage = LearningStage(
                id=str(uuid.uuid4()),
                version_id=version.id,
                title=stage_data["title"],
                description=stage_data.get("description"),
                stage_order=stage_data["stage_order"],
                outcome=stage_data.get("outcome"),
            )
            self.db.add(stage)
            if "stage_id" in stage_data:
                stage_id_map[stage_data["stage_id"]] = stage.id

        # Create nodes
        node_id_map = {}
        for node_data in nodes:
            node = LearningNode(
                id=str(uuid.uuid4()),
                version_id=version.id,
                stage_id=stage_id_map.get(node_data.get("stage_id")),
                title=node_data["title"],
                description=node_data.get("description"),
                node_order=node_data.get("node_order", 1),
                level=node_data.get("level", 1),
                difficulty=node_data.get("difficulty", "beginner"),
                estimated_minutes=node_data.get("estimated_minutes", 30),
                status="locked",
                learning_outcomes=json.dumps(node_data.get("learning_outcomes", [])),
                assessment_strategy=node_data.get("assessment_strategy"),
                generation_reason=node_data.get("generation_reason"),
            )
            self.db.add(node)
            if "node_id" in node_data:
                node_id_map[node_data["node_id"]] = node.id

        # Create edges
        for edge_data in edges:
            src_id = node_id_map.get(edge_data["source_node_id"], edge_data["source_node_id"])
            tgt_id = node_id_map.get(edge_data["target_node_id"], edge_data["target_node_id"])
            edge = LearningEdge(
                id=str(uuid.uuid4()),
                version_id=version.id,
                source_node_id=src_id,
                target_node_id=tgt_id,
            )
            self.db.add(edge)

        # Flush so nodes/edges are visible to subsequent queries
        await self.db.flush()

        # Mark root nodes (no prerequisites) as available even in draft phase
        await self._initialize_node_statuses(version.id)

        await self.db.commit()
        return version

    async def activate_version(
        self,
        path_id: str,
        user_id: str,
        version_id: str,
    ) -> LearningPath:
        """Activate a path version using CAS for concurrency safety."""
        path = await self.get_path(path_id, user_id)

        # Get the version
        result = await self.db.execute(
            select(LearningPathVersion).where(
                LearningPathVersion.id == version_id,
                LearningPathVersion.path_id == path_id,
            )
        )
        version = result.scalar_one_or_none()
        if not version:
            raise ApiError(code="VERSION_NOT_FOUND", message="Path version not found", status_code=404)

        if version.status not in ("draft", "in_review"):
            raise ApiError(code="INVALID_STATUS", message="Version cannot be activated", status_code=400)

        # CAS update
        expected_version = path.active_version_id
        result = await self.db.execute(
            update(LearningPath)
            .where(
                LearningPath.id == path_id,
                LearningPath.active_version_id.is_(expected_version)
                if expected_version is None
                else LearningPath.active_version_id == expected_version,
            )
            .values(active_version_id=version_id, status="active")
        )

        if not result.rowcount or result.rowcount != 1:  # type: ignore[attr-defined]
            raise ApiError(code="PATH_VERSION_CONFLICT", message="Version conflict detected", status_code=409)

        # Update version status
        version.status = "active"
        version.activated_at = utc_now()

        # Initialize node statuses: roots become available, others stay locked
        await self._initialize_node_statuses(version_id)

        # Update goal
        await self.db.execute(
            update(LearningGoal).where(LearningGoal.id == path.goal_id).values(status="active", current_path_id=path_id)
        )

        await self.db.flush()
        await self.db.commit()

        # Refresh path
        await self.db.refresh(path)
        return path

    async def create_revision_request(
        self,
        path_id: str,
        user_id: str,
        revision_request: str,
    ) -> LearningPathRevisionRequest:
        """Create a revision request for a path."""
        await self.get_path(path_id, user_id)

        request = LearningPathRevisionRequest(
            id=str(uuid.uuid4()),
            path_id=path_id,
            user_id=user_id,
            revision_request=revision_request,
        )
        self.db.add(request)
        await self.db.flush()
        await self.db.commit()
        return request

    async def list_versions(
        self,
        path_id: str,
        user_id: str,
    ) -> list[LearningPathVersion]:
        """List all versions of a path."""
        await self.get_path(path_id, user_id)  # Verify ownership

        result = await self.db.execute(
            select(LearningPathVersion)
            .where(LearningPathVersion.path_id == path_id)
            .order_by(LearningPathVersion.version_number.desc())
        )
        return list(result.scalars().all())

    async def _initialize_node_statuses(self, version_id: str) -> None:
        """Initialize node statuses after path activation."""
        # Get all nodes
        nodes_result = await self.db.execute(select(LearningNode).where(LearningNode.version_id == version_id))
        nodes = list(nodes_result.scalars().all())
        node_ids = {n.id for n in nodes}

        # Get all edges
        edges_result = await self.db.execute(select(LearningEdge).where(LearningEdge.version_id == version_id))
        edges = list(edges_result.scalars().all())

        # Find root nodes (no incoming edges)
        has_incoming = {e.target_node_id for e in edges if e.target_node_id in node_ids}

        for node in nodes:
            if node.id not in has_incoming:
                node.status = "available"
            # Others remain "locked"

    async def _format_path(
        self,
        path: LearningPath,
        version: LearningPathVersion | None,
        stages: list,
        nodes: list,
        edges: list,
    ) -> dict:
        """Format path data for API response."""
        # Use goal title as the path title (the user's original requirement)
        goal_title = ""
        if path.goal_id:
            goal_result = await self.db.execute(select(LearningGoal.title).where(LearningGoal.id == path.goal_id))
            goal_title = goal_result.scalar() or ""
        title = goal_title or (version.summary if version else "")
        return {
            "path_id": path.id,
            "goal_id": path.goal_id,
            "title": title,
            "description": None,
            "version": version.version_number if version else 1,
            "active_version": version.version_number if version else 1,
            "status": path.status,
            "current_node_id": None,
            "total_estimated_minutes": version.estimated_total_minutes if version else 0,
            "generation_summary": version.summary if version else None,
            "stages": [
                {
                    "stage_id": s.id,
                    "title": s.title,
                    "description": s.description,
                    "stage_order": s.stage_order,
                    "outcome": s.outcome,
                    "node_ids": [n.id for n in nodes if n.stage_id == s.id],
                }
                for s in stages
            ],
            "nodes": [
                {
                    "node_id": n.id,
                    "stage_id": n.stage_id,
                    "title": n.title,
                    "description": n.description,
                    "node_order": n.node_order,
                    "level": n.level,
                    "difficulty": n.difficulty,
                    "estimated_minutes": n.estimated_minutes,
                    "status": n.status,
                    "mastery": n.mastery,
                    "content_status": n.content_status,
                    "learning_outcomes": json.loads(n.learning_outcomes) if n.learning_outcomes else [],
                    "assessment_strategy": n.assessment_strategy,
                    "generation_reason": n.generation_reason,
                    "prerequisite_ids": [e.source_node_id for e in edges if e.target_node_id == n.id],
                    "next_node_ids": [e.target_node_id for e in edges if e.source_node_id == n.id],
                }
                for n in nodes
            ],
            "edges": [
                {
                    "edge_id": e.id,
                    "source_node_id": e.source_node_id,
                    "target_node_id": e.target_node_id,
                }
                for e in edges
            ],
            "created_at": to_iso_string(path.created_at),
            "updated_at": to_iso_string(path.updated_at),
        }

    async def list_user_paths(self, user_id: str) -> list[dict]:
        """List all non-archived learning paths for a user with progress stats."""
        result = await self.db.execute(
            select(LearningPath)
            .where(LearningPath.user_id == user_id, LearningPath.status != "archived")
            .order_by(LearningPath.updated_at.desc())
        )
        paths = list(result.scalars().all())

        items = []
        for path in paths:
            # Get the active version to find title and node counts
            title = ""
            total_nodes = 0
            estimated_minutes = 0

            # Prefer goal title (the user's original requirement)
            if path.goal_id:
                goal_result = await self.db.execute(select(LearningGoal.title).where(LearningGoal.id == path.goal_id))
                title = goal_result.scalar() or ""

            if path.active_version_id:
                ver_result = await self.db.execute(
                    select(LearningPathVersion).where(LearningPathVersion.id == path.active_version_id)
                )
                version = ver_result.scalar_one_or_none()
                if version:
                    if not title:
                        title = version.summary or ""
                    estimated_minutes = version.estimated_total_minutes

                    count_result = await self.db.execute(
                        select(func.count()).select_from(LearningNode).where(LearningNode.version_id == version.id)
                    )
                    total_nodes = count_result.scalar() or 0

            # Count completed nodes
            completed_result = await self.db.execute(
                select(func.count())
                .select_from(LearningProgress)
                .where(
                    LearningProgress.user_id == user_id,
                    LearningProgress.path_id == path.id,
                    LearningProgress.status == "completed",
                )
            )
            completed_nodes = completed_result.scalar() or 0
            progress = int((completed_nodes / total_nodes * 100) if total_nodes > 0 else 0)

            items.append(
                {
                    "path_id": path.id,
                    "goal_id": path.goal_id,
                    "title": title,
                    "status": path.status,
                    "progress": progress,
                    "completed_nodes": completed_nodes,
                    "total_nodes": total_nodes,
                    "estimated_minutes": estimated_minutes,
                    "created_at": to_iso_string(path.created_at),
                    "updated_at": to_iso_string(path.updated_at),
                }
            )

        return items

    async def delete_path(self, path_id: str, user_id: str) -> None:
        """Soft-delete a path by archiving it and its associated goal."""
        path = await self.get_path(path_id, user_id)

        # Archive the associated goal if it references this path
        goal_result = await self.db.execute(select(LearningGoal).where(LearningGoal.id == path.goal_id))
        goal = goal_result.scalar_one_or_none()
        if goal and goal.current_path_id == path_id and goal.status != "archived":
            goal.status = "archived"
            goal.updated_at = utc_now()

        # Archive the path
        path.status = "archived"
        path.updated_at = utc_now()

        await self.db.commit()
