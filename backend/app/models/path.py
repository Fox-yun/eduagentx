"""Learning path, version, stage, node, and edge models."""

from __future__ import annotations

import uuid
from collections import deque
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.errors import ApiError

if TYPE_CHECKING:
    from datetime import datetime


def generate_uuid() -> str:
    return str(uuid.uuid4())


class LearningPath(Base):
    """Learning path associated with a goal."""

    __tablename__ = "learning_paths"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    goal_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_goals.id"), nullable=False, index=True)
    active_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class LearningPathVersion(Base):
    """A version of a learning path."""

    __tablename__ = "learning_path_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    path_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_paths.id"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="initial_generation")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_total_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    generation_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str] = mapped_column(String(50), nullable=False, default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LearningStage(Base):
    """A stage within a learning path version."""

    __tablename__ = "learning_stages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("learning_path_versions.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    stage_order: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)


class LearningNode(Base):
    """A learning node within a path version."""

    __tablename__ = "learning_nodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("learning_path_versions.id"), nullable=False, index=True
    )
    stage_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("learning_stages.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    node_order: Mapped[int] = mapped_column(Integer, nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False, default="beginner")
    estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="locked")
    mastery: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    content_status: Mapped[str] = mapped_column(String(20), nullable=False, default="not_generated")
    learning_outcomes: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    assessment_strategy: Mapped[str | None] = mapped_column(Text, nullable=True)
    generation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class LearningEdge(Base):
    """A prerequisite edge between learning nodes."""

    __tablename__ = "learning_edges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("learning_path_versions.id"), nullable=False, index=True
    )
    source_node_id: Mapped[str] = mapped_column(String(36), nullable=False)
    target_node_id: Mapped[str] = mapped_column(String(36), nullable=False)


class LearningPathRevisionRequest(Base):
    """A user request to revise a learning path."""

    __tablename__ = "learning_path_revision_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    path_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_paths.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    revision_request: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# DAG Validation
def validate_dag(nodes: list[dict[str, str]], edges: list[dict[str, str]]) -> None:
    """Validate that the graph is a valid DAG.

    Checks:
    - Node IDs are unique
    - Edge endpoints exist
    - No self-loops
    - No cycles
    - At least one root (no incoming edges)
    - At least one leaf (no outgoing edges)
    - All required nodes reachable from roots
    """
    if not nodes:
        raise ApiError(code="INVALID_DAG", message="Path must have at least one node", status_code=400)

    node_ids = {n["id"] for n in nodes}

    # Check unique node IDs
    if len(node_ids) != len(nodes):
        raise ApiError(code="INVALID_DAG", message="Node IDs must be unique", status_code=400)

    # Build adjacency list
    outgoing: dict[str, set[str]] = {nid: set() for nid in node_ids}
    incoming: dict[str, set[str]] = {nid: set() for nid in node_ids}

    for edge in edges:
        src = edge["source_node_id"]
        tgt = edge["target_node_id"]

        if src not in node_ids or tgt not in node_ids:
            raise ApiError(code="INVALID_DAG", message=f"Edge endpoint not found: {src} -> {tgt}", status_code=400)

        if src == tgt:
            raise ApiError(code="INVALID_DAG", message="Self-loops are not allowed", status_code=400)

        outgoing[src].add(tgt)
        incoming[tgt].add(src)

    # Check for cycles using Kahn's algorithm
    in_degree = {nid: len(incoming[nid]) for nid in node_ids}
    queue = deque([nid for nid, deg in in_degree.items() if deg == 0])
    visited = 0

    while queue:
        node = queue.popleft()
        visited += 1
        for neighbor in outgoing[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if visited != len(node_ids):
        raise ApiError(code="INVALID_DAG", message="Graph contains a cycle", status_code=400)

    # Check roots and leaves
    roots = [nid for nid in node_ids if len(incoming[nid]) == 0]
    leaves = [nid for nid in node_ids if len(outgoing[nid]) == 0]

    if not roots:
        raise ApiError(code="INVALID_DAG", message="Graph must have at least one root node", status_code=400)

    if not leaves:
        raise ApiError(code="INVALID_DAG", message="Graph must have at least one leaf node", status_code=400)
