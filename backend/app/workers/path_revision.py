"""Learning path revision worker.

Generates a new path version based on a user's revision request,
without modifying the currently active version.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
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
from app.services.llm import LLMError, llm_json
from app.services.path import PathService
from app.workers.task_handlers import register_handler
from app.workers.task_runtime import update_task_status

logger = structlog.get_logger()


@register_handler("learning_path_revision")
async def execute_path_revision(db: Any, task: Any) -> dict[str, Any]:
    """Execute a learning path revision.

    Flow:
      1. Load the RevisionRequest and the current active version.
      2. Build an LLM prompt from the existing path + revision request.
      3. Generate a new path plan (stages / nodes / edges).
      4. DAG-validate the result.
      5. Create a new Version (in_review status) with PathService.
      6. Mark RevisionRequest as completed.
      7. Mark Task as completed.
    """
    revision_request_id = task.target_id
    metadata = task.target_metadata or {}
    path_id = metadata.get("path_id", "")
    user_id = task.user_id

    await update_task_status(db, task.id, "running", progress=5, stage="loading", message="正在加载修订请求...")

    # 1. Load revision request
    req_result = await db.execute(
        select(LearningPathRevisionRequest).where(LearningPathRevisionRequest.id == revision_request_id)
    )
    revision_req: LearningPathRevisionRequest | None = req_result.scalar_one_or_none()
    if not revision_req:
        raise ValueError(f"RevisionRequest {revision_request_id} not found")

    revision_req.status = "running"
    revision_req.started_at = utc_now()

    # 2. Load current active version
    path_result = await db.execute(select(LearningPath).where(LearningPath.id == path_id))
    path: LearningPath | None = path_result.scalar_one_or_none()
    if not path or not path.active_version_id:
        revision_req.status = "failed"
        revision_req.error = "Path has no active version"
        raise ValueError(f"Path {path_id} has no active version")

    active_version_id = path.active_version_id

    await update_task_status(db, task.id, "running", progress=15, stage="loading", message="正在分析当前学习路径...")

    # 3. Load current version details
    version_result = await db.execute(select(LearningPathVersion).where(LearningPathVersion.id == active_version_id))
    current_version: LearningPathVersion | None = version_result.scalar_one_or_none()
    if not current_version:
        revision_req.status = "failed"
        revision_req.error = "Active version not found"
        raise ValueError(f"Active version {active_version_id} not found")

    # Load stages
    stages_result = await db.execute(
        select(LearningStage).where(LearningStage.version_id == active_version_id).order_by(LearningStage.stage_order)
    )
    current_stages = list(stages_result.scalars().all())

    # Load nodes
    nodes_result = await db.execute(
        select(LearningNode).where(LearningNode.version_id == active_version_id).order_by(LearningNode.node_order)
    )
    current_nodes = list(nodes_result.scalars().all())

    # Load edges
    edges_result = await db.execute(select(LearningEdge).where(LearningEdge.version_id == active_version_id))
    current_edges = list(edges_result.scalars().all())

    await update_task_status(
        db, task.id, "running", progress=25, stage="generating", message="智能体正在生成修订方案..."
    )

    # 4. Build LLM prompt for revision
    current_path_summary = _build_current_path_summary(current_stages, current_nodes, current_edges)

    system_prompt = """你是一个专业的学习路径修订智能体。你的任务是根据用户的修订请求，对现有的学习路径进行优化和调整。

要求：
1. 保持路径的整体结构（阶段数量、节点数量可以调整）
2. 根据修订请求增加、删除或修改节点
3. 节点标题必须具体明确
4. 保持 DAG 结构（无循环依赖）
5. 输出完整的修订后路径

请以 JSON 格式输出，格式如下：
{
  "stages": [
    {"title": "阶段标题", "description": "阶段描述", "stage_order": 1, "outcome": "阶段学习成果"}
  ],
  "nodes": [
    {
      "node_id": "node-1",
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

    user_message = (
        f"## 当前学习路径\n\n{current_path_summary}\n\n"
        f"## 用户的修订请求\n\n{revision_req.revision_request}\n\n"
        f"请根据修订请求优化学习路径。"
    )

    # 5. Try LLM generation
    stages = []
    nodes = []
    edges = []
    summary = current_version.summary or "修订路径"
    revision_explanation = ""

    try:
        result = await llm_json(system_prompt, user_message, temperature=0.5, max_tokens=4096)

        stages = result.get("stages", [])
        nodes = result.get("nodes", [])
        edges = result.get("edges", [])
        summary = result.get("summary", summary)
        revision_explanation = result.get("revision_explanation", "")

        if len(nodes) < 3:
            raise LLMError("Too few nodes in revision")
        if len(nodes) > 15:
            nodes = nodes[:15]

        await update_task_status(
            db, task.id, "running", progress=60, stage="validating", message="正在校验修订后的路径结构..."
        )

    except Exception as e:
        logger.warning("llm_revision_fallback", error_type=type(e).__name__, error=str(e), exc_info=True)
        await update_task_status(
            db, task.id, "running", progress=35, stage="generating", message="LLM 不可用，使用模板修订..."
        )
        # Fallback: create a minimal revised version based on current structure
        stages = [
            {
                "title": s.title,
                "description": s.description,
                "stage_order": s.stage_order,
                "outcome": s.outcome,
            }
            for s in current_stages
        ]
        # Sort nodes to get consistent ordering
        sorted_nodes = sorted(current_nodes, key=lambda n: (n.node_order, n.level))
        nodes = []
        for n in sorted_nodes:
            nodes.append(
                {
                    "node_id": f"node-{n.node_order}",
                    "title": n.title,
                    "description": n.description or "",
                    "node_order": n.node_order,
                    "level": n.level,
                    "difficulty": n.difficulty,
                    "estimated_minutes": n.estimated_minutes,
                    "stage_id": f"stage-{_find_stage_order(current_stages, n.stage_id)}",
                    "learning_outcomes": json.loads(n.learning_outcomes) if n.learning_outcomes else [],
                }
            )
        edges = []
        for e in current_edges:
            source_order = _find_node_order(sorted_nodes, e.source_node_id)
            target_order = _find_node_order(sorted_nodes, e.target_node_id)
            if source_order and target_order:
                edges.append({"source_node_id": f"node-{source_order}", "target_node_id": f"node-{target_order}"})
        summary = f"{current_version.summary or '修订路径'} (模板修订)"
        revision_explanation = "基于当前路径结构的模板修订（LLM 不可用）"

    # 6. DAG validation
    validate_dag(nodes, edges)

    await update_task_status(db, task.id, "running", progress=75, stage="saving", message="正在保存修订版本...")

    # 7. Create new version
    path_service = PathService(db)
    new_version = await path_service.create_path_version(
        path_id=path_id,
        user_id=user_id,
        stages=stages,
        nodes=nodes,
        edges=edges,
        source="revision",
        summary=summary,
    )
    new_version.status = "in_review"
    new_version.parent_version_id = active_version_id
    new_version.generation_metadata = {
        "source": "revision",
        "revision_explanation": revision_explanation,
    }

    # 8. Update revision request
    revision_req.status = "completed"
    revision_req.generated_version_id = new_version.id
    revision_req.completed_at = utc_now()

    await db.flush()

    await update_task_status(db, task.id, "running", progress=100, stage="completed", message="路径修订完成")

    return {
        "path_id": path_id,
        "version_id": new_version.id,
        "version_number": new_version.version_number,
        "revision_explanation": revision_explanation,
    }


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
            lines.append(f"- {stage_label} 节点{n.node_order}: {n.title} ({n.difficulty}) — {outcomes_str}")

    if edges:
        lines.append("\n## 当前依赖关系")
        node_map = {n.id: f"节点{n.node_order}" for n in nodes}
        for e in edges:
            src = node_map.get(e.source_node_id, e.source_node_id[:8])
            tgt = node_map.get(e.target_node_id, e.target_node_id[:8])
            lines.append(f"- {src} → {tgt}")

    return "\n".join(lines) if lines else "（空路径）"


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
