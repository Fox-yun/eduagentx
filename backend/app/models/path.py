"""Learning path, version, stage, node, and edge models."""

from __future__ import annotations

import uuid
from collections import deque
from datetime import datetime  # noqa: TC003
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.errors import ApiError


def generate_uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Revision request state machine
# ---------------------------------------------------------------------------

REVISION_REQUEST_STATUSES: frozenset[str] = frozenset(
    {
        "pending",
        "running",
        "completed",
        "failed",
        "cancelled",
    }
)

ALLOWED_REVISION_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"running", "cancelled"}),
    "running": frozenset({"completed", "failed", "cancelled"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}


def validate_revision_transition(current: str, target: str) -> bool:
    """Validate that a revision request state transition is allowed."""
    allowed = ALLOWED_REVISION_TRANSITIONS.get(current, frozenset())
    return target in allowed


# ---------------------------------------------------------------------------
# Path version state machine
# ---------------------------------------------------------------------------

VERSION_STATUSES: frozenset[str] = frozenset(
    {
        "draft",
        "in_review",
        "active",
        "superseded",
        "invalid",
    }
)

ALLOWED_VERSION_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"in_review", "active", "invalid"}),
    "in_review": frozenset({"active", "superseded", "invalid"}),
    "active": frozenset({"superseded"}),
    "superseded": frozenset(),
    "invalid": frozenset(),
}


def validate_version_transition(current: str, target: str) -> bool:
    """Validate that a version state transition is allowed."""
    allowed = ALLOWED_VERSION_TRANSITIONS.get(current, frozenset())
    return target in allowed


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
    logical_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
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
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True, unique=True)
    source_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    generated_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True, unique=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# DAG Validation
def validate_dag(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    strict: bool = False,
) -> None:
    """Validate that the graph is a valid DAG.

    Checks:
    - Node IDs are unique
    - Edge endpoints exist
    - No self-loops
    - No duplicate edges (strict only)
    - No cycles
    - At least one root (no incoming edges)
    - All required nodes reachable from roots
    - Node estimated_minutes > 0 (strict only)
    - Node logical_key unique if present (strict only)
    """
    if not nodes:
        raise ApiError(code="INVALID_DAG", message="Path must have at least one node", status_code=400)

    raw_ids = [n.get("id") or n.get("node_id") for n in nodes]
    node_ids: set[str] = {nid for nid in raw_ids if nid is not None}

    if len(node_ids) != len(nodes):
        raise ApiError(code="INVALID_DAG", message="Node IDs must be unique", status_code=400)

    if strict:
        for n in nodes:
            if n.get("estimated_minutes", 0) <= 0:
                raise ApiError(
                    code="INVALID_DAG",
                    message=f"Node {n.get('node_id', n.get('id', '?'))} has invalid estimated_minutes",
                    status_code=400,
                )
            if n.get("node_order", 0) <= 0:
                raise ApiError(
                    code="INVALID_DAG",
                    message=f"Node {n.get('node_id', n.get('id', '?'))} has invalid node_order",
                    status_code=400,
                )

        logical_keys = [n.get("logical_key") for n in nodes if n.get("logical_key")]
        if len(logical_keys) != len(set(logical_keys)):
            raise ApiError(
                code="INVALID_DAG", message="Node logical_keys must be unique within a version", status_code=400
            )

    # Build adjacency list
    outgoing: dict[str, set[str]] = {nid: set() for nid in node_ids}
    incoming: dict[str, set[str]] = {nid: set() for nid in node_ids}

    edge_set: set[tuple[str, str]] = set()

    for edge in edges:
        src = edge["source_node_id"]
        tgt = edge["target_node_id"]

        if src not in node_ids or tgt not in node_ids:
            raise ApiError(code="INVALID_DAG", message=f"Edge endpoint not found: {src} -> {tgt}", status_code=400)

        if src == tgt:
            raise ApiError(code="INVALID_DAG", message="Self-loops are not allowed", status_code=400)

        if strict and (src, tgt) in edge_set:
            raise ApiError(code="INVALID_DAG", message=f"Duplicate edge: {src} -> {tgt}", status_code=400)

        edge_set.add((src, tgt))
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


def compute_node_diff(
    old_nodes: list[dict[str, Any]],
    new_nodes: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Compute diff between two node lists keyed by logical_key.

    Returns categorised lists:
      added: nodes in new but not in old
      removed: nodes in old but not in new
      modified: nodes in both with different content
      unchanged: nodes in both with same content
    """
    old_by_key: dict[str, dict[str, Any]] = {}
    for n in old_nodes:
        lk = n.get("logical_key")
        if lk:
            old_by_key[lk] = n

    new_by_key: dict[str, dict[str, Any]] = {}
    for n in new_nodes:
        lk = n.get("logical_key")
        if lk:
            new_by_key[lk] = n

    old_keys = set(old_by_key.keys())
    new_keys = set(new_by_key.keys())

    added_keys = new_keys - old_keys
    removed_keys = old_keys - new_keys
    common_keys = old_keys & new_keys

    added = [new_by_key[k] for k in added_keys]
    removed = [old_by_key[k] for k in removed_keys]

    modified: list[dict[str, Any]] = []
    unchanged: list[dict[str, Any]] = []

    COMPARED_FIELDS = {"title", "description", "difficulty", "estimated_minutes", "learning_outcomes"}

    for k in sorted(common_keys):
        old_n = old_by_key[k]
        new_n = new_by_key[k]
        if any(old_n.get(f) != new_n.get(f) for f in COMPARED_FIELDS):
            modified.append({**new_n, "_old": {f: old_n.get(f) for f in COMPARED_FIELDS}})
        else:
            unchanged.append(new_n)

    return {
        "added": added,
        "removed": removed,
        "modified": modified,
        "unchanged": unchanged,
    }
