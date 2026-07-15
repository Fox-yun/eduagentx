"""Learning path revision worker.

Generates a new path version based on a user's revision request,
without modifying the currently active version.

Dual-transaction pattern:
  Transaction A: Load data, mark revision as running → commit
  (no active transaction): LLM call, DAG validation
  Transaction B: Verify revision still running, create version → commit
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from app.common.datetime import utc_now
from app.models.path import (
    LearningEdge,
    LearningNode,
    LearningPath,
    LearningPathRevisionRequest,
    LearningPathVersion,
    LearningStage,
    validate_dag,
)
from app.services.llm import llm_json
from app.services.path import PathService
from app.workers.task_handlers import register_handler
from app.workers.task_runtime import update_task_status

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Structured schemas for revision output
# ---------------------------------------------------------------------------


class RevisedStage(BaseModel):
    """A stage within a revised learning path."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    stage_order: int = Field(ge=1, le=50)
    outcome: str | None = Field(None, max_length=1000)


class RevisedNode(BaseModel):
    """A node within a revised learning path."""

    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(min_length=1, max_length=50, pattern=r"^node-\d+$")
    logical_key: str | None = Field(None, min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    node_order: int = Field(ge=1, le=200)
    level: int = Field(ge=1, le=5)
    difficulty: str = Field(default="beginner", pattern=r"^(beginner|intermediate|advanced)$")
    estimated_minutes: int = Field(ge=5, le=300)
    stage_id: str = Field(min_length=1, max_length=50, pattern=r"^stage-\d+$")
    learning_outcomes: list[str] = Field(default_factory=list, max_length=10)


class RevisedEdge(BaseModel):
    """An edge within a revised learning path."""

    model_config = ConfigDict(extra="forbid")

    source_node_id: str = Field(min_length=1, max_length=50, pattern=r"^node-\d+$")
    target_node_id: str = Field(min_length=1, max_length=50, pattern=r"^node-\d+$")


class RevisedPathPlan(BaseModel):
    """Complete revised learning path plan from the LLM."""

    model_config = ConfigDict(extra="forbid")

    stages: list[RevisedStage] = Field(min_length=1, max_length=20)
    nodes: list[RevisedNode] = Field(min_length=3, max_length=30)
    edges: list[RevisedEdge] = Field(min_length=1)
    summary: str | None = Field(None, max_length=500)
    revision_explanation: str | None = Field(None, max_length=2000)

    @field_validator("edges")
    @classmethod
    def _validate_edge_node_ids(cls, v: list[RevisedEdge], info: Any) -> list[RevisedEdge]:
        """Validate that all edge source/target node_ids exist in nodes."""
        if not info.data.get("nodes"):
            return v
        valid_ids = {n.node_id for n in info.data["nodes"]}
        for edge in v:
            if edge.source_node_id not in valid_ids:
                raise ValueError(f"Edge source {edge.source_node_id} not found in nodes")
            if edge.target_node_id not in valid_ids:
                raise ValueError(f"Edge target {edge.target_node_id} not found in nodes")
        return v


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


@register_handler("learning_path_revision")
async def execute_path_revision(db: Any, task: Any) -> dict[str, Any]:
    """Execute a learning path revision using the dual-transaction pattern.

    Transaction A: Load data, mark revision as running, commit.
    (no transaction): Build prompt, call LLM, validate DAG.
    Transaction B: Verify revision still running, create version, commit.
    """
    revision_request_id = task.target_id
    metadata = task.target_metadata or {}
    path_id = metadata.get("path_id", "")
    user_id = task.user_id

    await update_task_status(db, task.id, "running", progress=5, stage="loading", message="正在加载修订请求...")

    # ==================================================================
    # Transaction A: Load data and mark revision as running
    # ==================================================================
    req_result = await db.execute(
        select(LearningPathRevisionRequest)
        .where(LearningPathRevisionRequest.id == revision_request_id)
        .with_for_update()
    )
    revision_req: LearningPathRevisionRequest | None = req_result.scalar_one_or_none()
    if not revision_req:
        raise ValueError(f"RevisionRequest {revision_request_id} not found")

    revision_req.status = "running"
    revision_req.started_at = utc_now()

    path_result = await db.execute(select(LearningPath).where(LearningPath.id == path_id).with_for_update())
    path: LearningPath | None = path_result.scalar_one_or_none()
    if not path:
        revision_req.status = "failed"
        revision_req.error = "Path not found"
        revision_req.completed_at = utc_now()
        await db.flush()
        await db.commit()
        raise ValueError(f"Path {path_id} not found")

    source_version_id = (
        metadata.get("source_version_id")
        or revision_req.source_version_id
        or path.active_version_id
    )
    if not source_version_id:
        revision_req.status = "failed"
        revision_req.error = "Path has no revision source version"
        revision_req.completed_at = utc_now()
        await db.flush()
        await db.commit()
        raise ValueError(f"Path {path_id} has no revision source version")

    await update_task_status(db, task.id, "running", progress=15, stage="loading", message="正在分析当前学习路径...")

    version_result = await db.execute(
        select(LearningPathVersion).where(
            LearningPathVersion.id == source_version_id,
            LearningPathVersion.path_id == path_id,
        )
    )
    current_version: LearningPathVersion | None = version_result.scalar_one_or_none()
    if not current_version:
        revision_req.status = "failed"
        revision_req.error = "Revision source version not found"
        revision_req.completed_at = utc_now()
        await db.flush()
        await db.commit()
        raise ValueError(f"Revision source version {source_version_id} not found")

    if current_version.status not in {"active", "draft", "in_review"}:
        revision_req.status = "failed"
        revision_req.error = f"Revision source version has invalid status: {current_version.status}"
        revision_req.completed_at = utc_now()
        await db.flush()
        await db.commit()
        raise ValueError(
            f"Revision source version {source_version_id} has invalid status: {current_version.status}"
        )

    stages_result = await db.execute(
        select(LearningStage).where(LearningStage.version_id == source_version_id).order_by(LearningStage.stage_order)
    )
    current_stages = list(stages_result.scalars().all())

    nodes_result = await db.execute(
        select(LearningNode).where(LearningNode.version_id == source_version_id).order_by(LearningNode.node_order)
    )
    current_nodes = list(nodes_result.scalars().all())

    edges_result = await db.execute(select(LearningEdge).where(LearningEdge.version_id == source_version_id))
    current_edges = list(edges_result.scalars().all())

    # Commit Transaction A — revision is now "running", data loaded in memory
    await db.flush()
    await db.commit()

    await update_task_status(
        db, task.id, "running", progress=25, stage="generating", message="智能体正在生成修订方案..."
    )

    # ==================================================================
    # Outside transaction: LLM call + validation
    # ==================================================================
    current_path_summary = _build_current_path_summary(current_stages, current_nodes, current_edges)

    system_prompt = _build_system_prompt()
    user_message = (
        f"## 当前学习路径\n\n{current_path_summary}\n\n"
        f"## 用户的修订请求\n\n{revision_req.revision_request}\n\n"
        f"请根据修订请求优化学习路径。"
    )

    plan: RevisedPathPlan | None = None
    try:
        raw_result = await llm_json(system_prompt, user_message, temperature=0.5, max_tokens=4096)
        plan = RevisedPathPlan.model_validate(raw_result)

        await update_task_status(
            db, task.id, "running", progress=60, stage="validating", message="正在校验修订后的路径结构..."
        )

    except Exception as e:
        logger.warning("llm_revision_fallback", error_type=type(e).__name__, error=str(e), exc_info=True)
        await update_task_status(
            db, task.id, "running", progress=35, stage="generating", message="LLM 不可用，使用模板修订..."
        )
        if current_version is None:
            raise RuntimeError("current_version is None during fallback path revision") from e
        plan = _build_fallback_plan(current_stages, current_nodes, current_edges, current_version)

    # Build raw dicts for DAG validation
    node_dicts = [_node_to_dict(n) for n in plan.nodes]
    edge_dicts = [{"source_node_id": e.source_node_id, "target_node_id": e.target_node_id} for e in plan.edges]

    validate_dag(node_dicts, edge_dicts, strict=True)

    # ==================================================================
    # Transaction B: Verify revision still valid + create version
    # ==================================================================
    await update_task_status(db, task.id, "running", progress=75, stage="saving", message="正在保存修订版本...")

    # Verify revision is still in running state (not cancelled)
    verify_result = await db.execute(
        select(LearningPathRevisionRequest)
        .where(LearningPathRevisionRequest.id == revision_request_id)
        .with_for_update()
    )
    current_req = verify_result.scalar_one_or_none()
    if current_req is None or current_req.status != "running":
        raise ValueError(f"Revision request {revision_request_id} is no longer in running state")

    path_service = PathService(db)
    new_version = await path_service.create_path_version(
        path_id=path_id,
        user_id=user_id,
        stages=[s.model_dump() for s in plan.stages],
        nodes=node_dicts,
        edges=edge_dicts,
        source="revision",
        summary=plan.summary,
    )
    new_version.status = "in_review"
    new_version.parent_version_id = source_version_id
    new_version.generation_metadata = {
        "source": "revision",
        "revision_explanation": plan.revision_explanation,
    }

    revision_req.status = "completed"
    revision_req.generated_version_id = new_version.id
    revision_req.completed_at = utc_now()

    await db.flush()
    await db.commit()

    await update_task_status(db, task.id, "running", progress=100, stage="completed", message="路径修订完成")

    return {
        "path_id": path_id,
        "version_id": new_version.id,
        "version_number": new_version.version_number,
        "revision_explanation": plan.revision_explanation or "",
    }


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------


def _build_system_prompt() -> str:
    return """你是一个专业的学习路径修订智能体。你的任务是根据用户的修订请求，对现有的学习路径进行优化和调整。

输出规范：
1. 保持节点的 `logical_key` 稳定 —— 如果节点核心内容未变，使用相同的 logical_key
2. 新增节点使用新的 logical_key（格式：`module.subtopic.concept`）
3. 节点标题必须具体明确
4. 保持 DAG 结构（无循环依赖）
5. 每个节点必须包含 node_id（格式 node-1, node-2...）和 stage_id（格式 stage-1, stage-2...）

请以 JSON 格式输出，格式如下：
{
  "stages": [
    {"title": "阶段标题", "description": "阶段描述", "stage_order": 1, "outcome": "阶段学习成果"}
  ],
  "nodes": [
    {
      "node_id": "node-1",
      "logical_key": "module.subtopic.concept",
      "title": "具体的知识点标题",
      "description": "该节点要学习的具体内容描述",
      "node_order": 1,
      "level": 1,
      "difficulty": "beginner|intermediate|advanced",
      "estimated_minutes": 30,
      "stage_id": "stage-1",
      "learning_outcomes": ["具体的学习成果1", "具体的学习成果2"]
    }
  ],
  "edges": [
    {"source_node_id": "node-1", "target_node_id": "node-2"}
  ],
  "summary": "路径摘要",
  "revision_explanation": "对本次修订的简要说明"
}"""


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------


def _build_fallback_plan(
    current_stages: list[LearningStage],
    current_nodes: list[LearningNode],
    current_edges: list[LearningEdge],
    current_version: LearningPathVersion,
) -> RevisedPathPlan:
    """Build a template-based revision plan when LLM is unavailable."""
    stages = [
        RevisedStage(
            title=s.title,
            description=s.description,
            stage_order=s.stage_order,
            outcome=s.outcome,
        )
        for s in current_stages
    ]

    sorted_nodes = sorted(current_nodes, key=lambda n: (n.node_order, n.level))
    nodes: list[RevisedNode] = []
    for n in sorted_nodes:
        nodes.append(
            RevisedNode(
                node_id=f"node-{n.node_order}",
                logical_key=n.logical_key,
                title=n.title,
                description=n.description or "",
                node_order=n.node_order,
                level=n.level,
                difficulty=n.difficulty,
                estimated_minutes=n.estimated_minutes,
                stage_id=f"stage-{_find_stage_order(current_stages, n.stage_id)}",
                learning_outcomes=json.loads(n.learning_outcomes) if n.learning_outcomes else [],
            )
        )

    edges: list[RevisedEdge] = []
    nodes_sorted = sorted(current_nodes, key=lambda n: (n.node_order, n.level))
    for e in current_edges:
        source_order = _find_node_order(nodes_sorted, e.source_node_id)
        target_order = _find_node_order(nodes_sorted, e.target_node_id)
        if source_order and target_order:
            edges.append(
                RevisedEdge(
                    source_node_id=f"node-{source_order}",
                    target_node_id=f"node-{target_order}",
                )
            )

    summary = (current_version.summary or "修订路径") + " (模板修订)"
    revision_explanation = "基于当前路径结构的模板修订（LLM 不可用）"

    return RevisedPathPlan(
        stages=stages, nodes=nodes, edges=edges, summary=summary, revision_explanation=revision_explanation
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_current_path_summary(
    stages: list[LearningStage],
    nodes: list[LearningNode],
    edges: list[LearningEdge],
) -> str:
    """Build a text summary of the current path for the LLM prompt."""
    lines = []

    if stages:
        lines.append("## 当前阶段")
        for s in stages:
            lines.append(f"- 阶段 {s.stage_order}: {s.title}")

    if nodes:
        lines.append("\n## 当前节点")
        for n in sorted(nodes, key=lambda x: (x.node_order, x.level)):
            outcomes = json.loads(n.learning_outcomes) if n.learning_outcomes else []
            outcomes_str = "; ".join(outcomes[:3]) if outcomes else "无"
            stage_label = f"[阶段 {_find_stage_order(stages, n.stage_id)}]" if n.stage_id else ""
            logical_key_str = f" ({n.logical_key})" if n.logical_key else ""
            lines.append(
                f"- {stage_label} 节点{n.node_order}{logical_key_str}: {n.title} ({n.difficulty}) — {outcomes_str}"
            )

    if edges:
        lines.append("\n## 当前依赖关系")
        node_map = {n.id: f"节点{n.node_order}" for n in nodes}
        for e in edges:
            src = node_map.get(e.source_node_id, e.source_node_id[:8])
            tgt = node_map.get(e.target_node_id, e.target_node_id[:8])
            lines.append(f"- {src} → {tgt}")

    return "\n".join(lines) if lines else "（空路径）"


def _node_to_dict(n: RevisedNode) -> dict[str, Any]:
    """Convert a RevisedNode to a dict for DAG validation and PathService."""
    result: dict[str, Any] = {
        "node_id": n.node_id,
        "logical_key": n.logical_key,
        "title": n.title,
        "description": n.description,
        "node_order": n.node_order,
        "level": n.level,
        "difficulty": n.difficulty,
        "estimated_minutes": n.estimated_minutes,
        "stage_id": n.stage_id,
        "learning_outcomes": n.learning_outcomes,
    }
    return result


def _find_stage_order(stages: list[LearningStage], stage_id: str | None) -> int:
    """Find the stage_order for a given stage_id."""
    if not stage_id:
        return 1
    for s in stages:
        if s.id == stage_id:
            return s.stage_order
    return 1


def _find_node_order(nodes: list[LearningNode], node_id: str) -> int | None:
    """Find the node_order for a given node_id."""
    for n in nodes:
        if n.id == node_id:
            return n.node_order
    return None
