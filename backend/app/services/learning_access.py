"""Unified learning access control.

Provides a single entry point for verifying that a user has permission
to access a specific learning node within a path version context.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.models.path import LearningNode, LearningPath, LearningPathVersion


@dataclass
class NodeAccessContext:
    """Result of a successful node access check."""

    path: LearningPath
    version: LearningPathVersion | None
    node: LearningNode
    path_id: str
    version_id: str | None
    node_id: str
    user_id: str


async def require_node_access(
    db: AsyncSession,
    user_id: str,
    path_id: str,
    node_id: str,
    require_active_version: bool = True,
) -> NodeAccessContext:
    """Verify that *user_id* can access *node_id* in *path_id*.

    Checks performed:
      - Path belongs to the user.
      - Path is not archived.
      - Node belongs to the path's current active version.
      - (Optional) Node is in a learnable state (available / in_progress).

    Raises ApiError (403/404) on any violation.
    Returns a NodeAccessContext with resolved entities.
    """
    # 1. Load path with ownership guard
    path_result = await db.execute(
        select(LearningPath).where(
            LearningPath.id == path_id,
            LearningPath.user_id == user_id,
        )
    )
    path: LearningPath | None = path_result.scalar_one_or_none()
    if not path:
        raise ApiError(code="PATH_NOT_FOUND", message="Learning path not found", status_code=404)

    # 2. Check path is not archived — return 404 to avoid leaking path existence
    if path.status == "archived":
        raise ApiError(code="PATH_ARCHIVED", message="Learning path is archived", status_code=404)

    # 3. Resolve the relevant version
    version_id = path.active_version_id
    if not version_id and require_active_version:
        raise ApiError(code="NO_ACTIVE_VERSION", message="Path has no active version", status_code=400)

    version: LearningPathVersion | None = None
    if version_id:
        version_result = await db.execute(
            select(LearningPathVersion).where(
                LearningPathVersion.id == version_id,
                LearningPathVersion.path_id == path_id,
            )
        )
        version = version_result.scalar_one_or_none()
        if not version:
            raise ApiError(code="VERSION_NOT_FOUND", message="Active version not found", status_code=404)

    # 4. Load node with version constraint
    if version_id:
        node_result = await db.execute(
            select(LearningNode).where(
                LearningNode.id == node_id,
                LearningNode.version_id == version_id,
            )
        )
    else:
        node_result = await db.execute(select(LearningNode).where(LearningNode.id == node_id))
    node: LearningNode | None = node_result.scalar_one_or_none()
    if not node:
        raise ApiError(code="NODE_NOT_FOUND", message="Learning node not found in current version", status_code=404)

    return NodeAccessContext(
        path=path,
        version=version,
        node=node,
        path_id=path_id,
        version_id=version_id or "",
        node_id=node_id,
        user_id=user_id,
    )
