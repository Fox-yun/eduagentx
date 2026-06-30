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
from app.models.task import BackgroundTask

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
                logical_key=node_data.get("logical_key"),
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
        """Activate a path version using CAS for concurrency safety.

        Transaction:
          1. Lock the path row (FOR UPDATE)
          2. Verify the target version exists, belongs to this path, and is in_review
          3. Read old active version and supersede it
          4. Migrate progress from old node IDs to new node IDs (by logical_key)
          5. Set new version to active, update path reference
          6. Commit
        """
        # 1. Lock path row
        result = await self.db.execute(
            select(LearningPath)
            .where(
                LearningPath.id == path_id,
                LearningPath.user_id == user_id,
            )
            .with_for_update()
        )
        path = result.scalar_one_or_none()
        if not path:
            raise ApiError(code="PATH_NOT_FOUND", message="Learning path not found", status_code=404)

        # 2. Verify the target version
        ver_result = await self.db.execute(
            select(LearningPathVersion).where(
                LearningPathVersion.id == version_id,
                LearningPathVersion.path_id == path_id,
            )
        )
        version = ver_result.scalar_one_or_none()
        if not version:
            raise ApiError(code="VERSION_NOT_FOUND", message="Path version not found", status_code=404)

        from app.models.path import validate_version_transition

        if not validate_version_transition(version.status, "active"):
            raise ApiError(
                code="INVALID_STATUS",
                message=f"Version status '{version.status}' cannot be activated",
                status_code=400,
            )

        # 3. Supersede old active version
        old_active_version_id = path.active_version_id
        if old_active_version_id and old_active_version_id != version_id:
            old_ver_result = await self.db.execute(
                select(LearningPathVersion).where(LearningPathVersion.id == old_active_version_id)
            )
            old_version = old_ver_result.scalar_one_or_none()
            if old_version and old_version.status == "active":
                old_version.status = "superseded"

        # 4. Migrate progress from old nodes to new nodes by logical_key
        await self._migrate_progress(path_id, user_id, old_active_version_id, version_id)

        # 5. Set new version as active
        version.status = "active"
        version.activated_at = utc_now()
        path.active_version_id = version_id
        path.status = "active"

        # Initialize root node statuses
        await self._initialize_node_statuses(version_id)

        # Update goal
        await self.db.execute(
            update(LearningGoal).where(LearningGoal.id == path.goal_id).values(status="active", current_path_id=path_id)
        )

        await self.db.flush()
        await self.db.commit()

        await self.db.refresh(path)
        return path

    async def _migrate_progress(
        self,
        path_id: str,
        user_id: str,
        old_version_id: str | None,
        new_version_id: str,
    ) -> None:
        """Migrate learning progress from old version nodes to new version nodes.

        Matching is done by logical_key. Rules:
        - Same logical_key + existed before → retain completed status and mastery
        - Same logical_key but different content → retain history, mark as inherited
        - New logical_key → leave as default (available/locked based on prerequisites)
        - Old logical_key removed → progress stays with old version (no deletion)
        """
        if not old_version_id:
            return

        # Get old and new nodes
        old_nodes_result = await self.db.execute(select(LearningNode).where(LearningNode.version_id == old_version_id))
        old_nodes = list(old_nodes_result.scalars().all())

        new_nodes_result = await self.db.execute(select(LearningNode).where(LearningNode.version_id == new_version_id))
        new_nodes = list(new_nodes_result.scalars().all())

        # Build logical_key → node_id maps
        old_by_key: dict[str, str] = {}
        for n in old_nodes:
            if n.logical_key:
                old_by_key[n.logical_key] = n.id

        new_by_key: dict[str, str] = {}
        for n in new_nodes:
            if n.logical_key:
                new_by_key[n.logical_key] = n.id

        if not old_by_key and not new_by_key:
            return  # No logical_keys on either side — skip migration

        # Get existing progress for all old nodes
        old_node_ids = list(old_by_key.values())
        if not old_node_ids:
            return

        progress_result = await self.db.execute(
            select(LearningProgress).where(
                LearningProgress.user_id == user_id,
                LearningProgress.path_id == path_id,
                LearningProgress.node_id.in_(old_node_ids),
            )
        )
        existing_progress = list(progress_result.scalars().all())

        # Map old node_id → progress
        progress_by_old_node: dict[str, LearningProgress] = {p.node_id: p for p in existing_progress}

        # Migrate: for each old progress entry with a matching logical_key in new version,
        # create or update progress on the new node
        for old_lk, old_nid in old_by_key.items():
            if old_lk not in new_by_key:
                continue  # Node was removed — keep old progress as-is
            if old_nid not in progress_by_old_node:
                continue  # No progress to migrate

            new_nid = new_by_key[old_lk]
            old_progress = progress_by_old_node[old_nid]

            # Check if new progress already exists
            existing_new = await self.db.execute(
                select(LearningProgress).where(
                    LearningProgress.user_id == user_id,
                    LearningProgress.path_id == path_id,
                    LearningProgress.node_id == new_nid,
                )
            )
            if existing_new.scalar_one_or_none():
                continue  # Already migrated

            # Create migrated progress entry for the new node
            new_progress = LearningProgress(
                id=str(uuid.uuid4()),
                user_id=user_id,
                path_id=path_id,
                node_id=new_nid,
                status=old_progress.status,
                mastery=old_progress.mastery,
                attempts=old_progress.attempts,
                completed_at=old_progress.completed_at,
            )
            self.db.add(new_progress)

    async def create_revision_request(
        self,
        path_id: str,
        user_id: str,
        revision_request: str,
    ) -> tuple[LearningPathRevisionRequest, BackgroundTask | None]:
        """Create a revision request and enqueue a background task.

        Uses SELECT ... FOR UPDATE to prevent concurrent revision creation.
        Checks for existing pending/running revisions on the same path.
        Returns (revision_request, background_task | None).
        Both are created atomically in the same transaction (no commit).
        The caller must commit.
        """
        from app.services.task import TaskService

        # Lock the path row to prevent concurrent revision requests
        result = await self.db.execute(
            select(LearningPath)
            .where(
                LearningPath.id == path_id,
                LearningPath.user_id == user_id,
            )
            .with_for_update()
        )
        path = result.scalar_one_or_none()
        if not path:
            raise ApiError(code="PATH_NOT_FOUND", message="Learning path not found", status_code=404)

        if path.status == "archived":
            raise ApiError(code="PATH_ARCHIVED", message="Cannot revise an archived path", status_code=403)

        # Confirm there is a current active version to base the revision on
        if not path.active_version_id:
            raise ApiError(code="NO_ACTIVE_VERSION", message="Path has no active version to revise", status_code=400)

        # Check for existing pending or running revision requests on this path
        existing_result = await self.db.execute(
            select(LearningPathRevisionRequest)
            .where(
                LearningPathRevisionRequest.path_id == path_id,
                LearningPathRevisionRequest.status.in_({"pending", "running"}),
            )
            .limit(1)
        )
        existing = existing_result.scalar_one_or_none()
        if existing:
            # Return the existing revision request and its task (if any)
            task = None
            if existing.task_id:
                task_result = await self.db.execute(select(BackgroundTask).where(BackgroundTask.id == existing.task_id))
                task = task_result.scalar_one_or_none()
            return existing, task

        idempotency_key = f"path-revision:{path_id}:{path.active_version_id}:{revision_request[:64]}"

        request = LearningPathRevisionRequest(
            id=str(uuid.uuid4()),
            path_id=path_id,
            user_id=user_id,
            revision_request=revision_request,
            source_version_id=path.active_version_id,
        )
        self.db.add(request)
        await self.db.flush()

        task_service = TaskService(self.db)
        task = await task_service.enqueue_task(
            user_id=user_id,
            task_type="learning_path_revision",
            target_type="revision_request",
            target_id=request.id,
            target_metadata={
                "path_id": path_id,
                "source_version_id": path.active_version_id,
            },
            idempotency_key=idempotency_key,
        )

        # Link task back to revision request
        request.task_id = task.id

        return request, task

    async def get_version_with_details(
        self,
        path_id: str,
        user_id: str,
        version_id: str,
    ) -> dict:
        """Get a specific version with its stages, nodes, and edges."""
        await self.get_path(path_id, user_id)

        result = await self.db.execute(
            select(LearningPathVersion).where(
                LearningPathVersion.id == version_id,
                LearningPathVersion.path_id == path_id,
            )
        )
        version = result.scalar_one_or_none()
        if not version:
            raise ApiError(code="VERSION_NOT_FOUND", message="Path version not found", status_code=404)

        stages_result = await self.db.execute(
            select(LearningStage).where(LearningStage.version_id == version.id).order_by(LearningStage.stage_order)
        )
        stages = list(stages_result.scalars().all())

        nodes_result = await self.db.execute(
            select(LearningNode).where(LearningNode.version_id == version.id).order_by(LearningNode.node_order)
        )
        nodes = list(nodes_result.scalars().all())

        edges_result = await self.db.execute(select(LearningEdge).where(LearningEdge.version_id == version.id))
        edges = list(edges_result.scalars().all())

        path = await self.get_path(path_id, user_id)
        return await self._format_path(path, version, stages, nodes, edges)

    async def compute_version_diff(
        self,
        path_id: str,
        user_id: str,
        version_id: str,
    ) -> dict:
        """Compute diff between the active version and a candidate version.

        Uses logical_key for node matching.
        """
        path = await self.get_path(path_id, user_id)

        # Get the candidate version
        cand_result = await self.db.execute(
            select(LearningPathVersion).where(
                LearningPathVersion.id == version_id,
                LearningPathVersion.path_id == path_id,
            )
        )
        candidate = cand_result.scalar_one_or_none()
        if not candidate:
            raise ApiError(code="VERSION_NOT_FOUND", message="Path version not found", status_code=404)

        # Get the active version
        if not path.active_version_id:
            raise ApiError(code="NO_ACTIVE_VERSION", message="Path has no active version", status_code=400)

        active_result = await self.db.execute(
            select(LearningPathVersion).where(LearningPathVersion.id == path.active_version_id)
        )
        active = active_result.scalar_one_or_none()
        if not active:
            raise ApiError(code="ACTIVE_VERSION_NOT_FOUND", message="Active version not found", status_code=404)

        # Get nodes for both versions
        active_nodes_result = await self.db.execute(select(LearningNode).where(LearningNode.version_id == active.id))
        active_nodes = list(active_nodes_result.scalars().all())

        cand_nodes_result = await self.db.execute(select(LearningNode).where(LearningNode.version_id == candidate.id))
        cand_nodes = list(cand_nodes_result.scalars().all())

        # Build logical_key maps
        active_by_key: dict[str, LearningNode] = {}
        for n in active_nodes:
            if n.logical_key:
                active_by_key[n.logical_key] = n

        cand_by_key: dict[str, LearningNode] = {}
        for n in cand_nodes:
            if n.logical_key:
                cand_by_key[n.logical_key] = n

        active_keys = set(active_by_key.keys())
        cand_keys = set(cand_by_key.keys())

        added_keys = cand_keys - active_keys
        removed_keys = active_keys - cand_keys
        common_keys = active_keys & cand_keys

        COMPARED_FIELDS = {"title", "description", "difficulty", "estimated_minutes"}

        added = []
        for k in sorted(added_keys):
            n = cand_by_key[k]
            added.append(
                {
                    "logical_key": k,
                    "title": n.title,
                    "description": n.description,
                    "difficulty": n.difficulty,
                    "estimated_minutes": n.estimated_minutes,
                }
            )

        removed = []
        for k in sorted(removed_keys):
            n = active_by_key[k]
            removed.append(
                {
                    "logical_key": k,
                    "title": n.title,
                    "description": n.description,
                    "difficulty": n.difficulty,
                    "estimated_minutes": n.estimated_minutes,
                }
            )

        modified = []
        for k in sorted(common_keys):
            old_n = active_by_key[k]
            new_n = cand_by_key[k]
            changes = {}
            for f in COMPARED_FIELDS:
                old_val = getattr(old_n, f, None)
                new_val = getattr(new_n, f, None)
                if old_val != new_val:
                    changes[f] = {"old": old_val, "new": new_val}
            if changes:
                modified.append(
                    {
                        "logical_key": k,
                        "title": new_n.title,
                        "changes": changes,
                    }
                )

        # Calculate time delta
        old_total = sum(n.estimated_minutes for n in active_nodes)
        new_total = sum(n.estimated_minutes for n in cand_nodes)
        estimated_minutes_delta = new_total - old_total

        return {
            "active_version_id": active.id,
            "active_version_number": active.version_number,
            "candidate_version_id": candidate.id,
            "candidate_version_number": candidate.version_number,
            "added_nodes": added,
            "removed_nodes": removed,
            "modified_nodes": modified,
            "unchanged_count": len(common_keys) - len(modified),
            "estimated_minutes_delta": estimated_minutes_delta,
            "difficulty_delta": "increased"
            if new_total > old_total
            else ("decreased" if new_total < old_total else "unchanged"),
        }

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
                    "logical_key": n.logical_key,
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
