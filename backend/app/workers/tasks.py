"""Celery worker tasks."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from app.core.database import get_session_factory
from app.workers.celery_app import celery_app
from app.workers.task_handlers import get_handler, register_handler
from app.workers.task_runtime import record_agent_step, recover_stale_tasks, update_task_status

logger = structlog.get_logger()


def run_async(coro: Any) -> Any:
    """Run an async function in a sync context.

    Reuses the current event loop if one exists, otherwise creates a new one.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Already inside an event loop (e.g. Jupyter) — use nest_asyncio or fallback
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()

    return asyncio.run(coro)


@celery_app.task(bind=True, name="tasks.execute_background_task")  # type: ignore[untyped-decorator]
def execute_background_task(self: Any, task_id: str) -> dict[str, Any]:
    """Execute a background task based on its type."""
    logger.info("executing_task", task_id=task_id)

    factory = get_session_factory()

    async def _execute() -> dict[str, Any]:
        async with factory() as db:
            # Get task
            from sqlalchemy import select

            from app.models.task import BackgroundTask

            result = await db.execute(select(BackgroundTask).where(BackgroundTask.id == task_id))
            task = result.scalar_one_or_none()

            if not task:
                logger.error("task_not_found", task_id=task_id)
                return {"status": "error", "message": "Task not found"}

            # Update to running
            await update_task_status(db, task_id, "running", progress=0, stage="starting", message="Task started")

            # Execute based on task type
            try:
                handler = get_handler(task.task_type)
                if handler is None:
                    await update_task_status(
                        db,
                        task.id,
                        "failed",
                        error_code="UNKNOWN_TASK_TYPE",
                        error_message=f"Unknown task type: {task.task_type}",
                    )
                    return {"status": "error", "message": f"Unknown task type: {task.task_type}"}

                task_result = await handler(db, task)

                # Mark completed
                await update_task_status(
                    db,
                    task_id,
                    "completed",
                    progress=100,
                    stage="completed",
                    message="Task completed",
                    result=task_result,
                )

                return {"status": "completed", "result": task_result}

            except Exception as e:
                logger.error("task_execution_failed", task_id=task_id, error=str(e))
                await update_task_status(db, task_id, "failed", error_code="EXECUTION_ERROR", error_message=str(e))

                # Transition goal to "failed" so user can retry
                if task.task_type in ("learning_path_generation", "learning_unit_generation") and task.target_id:
                    try:
                        from app.models.goal import LearningGoal

                        goal_row: LearningGoal | None = None
                        if task.task_type == "learning_path_generation":
                            # For path generation, target_id IS the goal_id
                            goal_result = await db.execute(
                                select(LearningGoal).where(LearningGoal.id == task.target_id)
                            )
                            goal_row = goal_result.scalar_one_or_none()
                        else:
                            # For unit generation, target_id is the node_id — look up goal via path version and path
                            from app.models.path import LearningNode, LearningPath, LearningPathVersion

                            goal_result = await db.execute(
                                select(LearningGoal)
                                .join(LearningPath, LearningPath.goal_id == LearningGoal.id)
                                .join(LearningPathVersion, LearningPathVersion.path_id == LearningPath.id)
                                .join(LearningNode, LearningNode.version_id == LearningPathVersion.id)
                                .where(LearningNode.id == task.target_id)
                            )
                            goal_row = goal_result.scalar_one_or_none()

                        if goal_row and goal_row.status not in ("failed", "archived", "draft"):
                            goal_row.status = "failed"
                            goal_row.active_task_id = None
                            await db.flush()
                            await db.commit()
                    except Exception:
                        logger.warning("goal_transition_failed_on_error", task_id=task_id)

                # For diagnostic_grading failure, transition attempt back to submitted
                if task.task_type == "diagnostic_grading" and task.target_id:
                    try:
                        from app.models.diagnostic import DiagnosticAttempt as DAttempt

                        attempt_result = await db.execute(select(DAttempt).where(DAttempt.id == task.target_id))
                        attempt_row = attempt_result.scalar_one_or_none()
                        if attempt_row and attempt_row.status == "grading":
                            attempt_row.status = "submitted"
                            await db.flush()
                            await db.commit()
                    except Exception:
                        logger.warning("diagnostic_attempt_recovery_failed", task_id=task_id)

                return {"status": "error", "message": str(e)}
            finally:
                await _cleanup_engine()

    return run_async(_execute())  # type: ignore[no-any-return]


async def _cleanup_engine() -> None:
    """Dispose the global engine to prevent stale connections across asyncio.run() calls."""
    from app.core.database import get_engine

    engine = get_engine()
    await engine.dispose()


@register_handler("e2e_progress_test")
async def _execute_e2e_progress_task(db: Any, task: Any) -> dict[str, Any]:
    """Execute a deterministic E2E progress task.

    Produces a fixed sequence: running 10% → 40% → 70% → completed 100%.
    Each step has a short delay so SSE clients can observe the progression.
    """
    import asyncio

    await update_task_status(db, task.id, "running", progress=10, stage="starting", message="E2E starting")
    await asyncio.sleep(0.3)

    await update_task_status(db, task.id, "running", progress=40, stage="processing", message="E2E processing")
    await asyncio.sleep(0.3)

    await update_task_status(db, task.id, "running", progress=70, stage="finalizing", message="E2E finalizing")
    await asyncio.sleep(0.3)

    return {"result": "e2e progress completed"}


def _extract_topic(goal_title: str) -> str:
    """Extract the core topic from a goal title by stripping common intent prefixes."""
    import re

    title = goal_title.strip()
    # Strip common Chinese intent prefixes
    patterns = [
        r"^(我希望|我想要|我想|我要|我需要|请帮我|帮我|请|希望|想要|需要)(学习|掌握|了解|学会|精通|研究|探索)?",
        r"^(学习|掌握|了解|学会|精通|研究|探索)\s*",
        r"^(learn|study|master|understand|i want to|i'd like to|please)\s+",
    ]
    for pat in patterns:
        title = re.sub(pat, "", title, flags=re.IGNORECASE).strip()
    # If stripping left nothing meaningful, return original
    return title if len(title) >= 2 else goal_title.strip()


@register_handler("learning_path_generation")
async def _execute_path_generation(db: Any, task: Any) -> dict[str, Any]:
    """Execute a path generation task using LLM to create 5-15 learning nodes."""
    import asyncio
    import uuid

    from app.services.goal import GoalService
    from app.services.llm import LLMError, llm_json
    from app.services.path import PathService

    goal_id = task.target_id
    user_id = task.user_id

    await update_task_status(db, task.id, "running", progress=10, stage="analyzing", message="正在分析学习目标...")

    goal_service = GoalService(db)
    goal = await goal_service.get_goal(goal_id, user_id)

    await asyncio.sleep(1)
    await update_task_status(
        db, task.id, "running", progress=20, stage="analyzing", message="智能体正在评估知识结构，规划学习节点..."
    )

    # Build LLM prompt for path generation
    system_prompt = """你是一个专业的学习路径规划智能体。你的任务是根据用户的学习目标，生成一个结构化的学习路径。

要求：
1. 生成 5-15 个学习节点（units），每个节点是一个具体的知识点或技能
2. 节点标题必须准确描述该节点要学习的具体内容（不要使用"基础概念"、"进阶应用"这样的泛化标题）
3. 【重要】从用户的学习目标中提取核心主题词，不要直接使用用户目标的完整表述。
   例如：目标是"我希望学习C++基础"时，标题应以"C++"开头（如"C++变量与数据类型"），
   而不是"我希望学习C++基础的变量与数据类型"
4. 每个节点包含 description、difficulty、estimated_minutes、learning_outcomes
5. 节点之间通过 edges 定义前置依赖关系（DAG 结构）
6. 节点按学习顺序排列，从基础到高级
7. 将节点分组到 2-4 个 stages（阶段）

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
  "summary": "路径摘要"
}"""

    topic = _extract_topic(goal.title)

    # Phase 3.6-D: Load student profile for personalised path planning
    profile_context = ""
    try:
        from app.services.profile_merge import load_profile_context

        _profile, profile_context = await load_profile_context(db, user_id)
    except Exception as e:
        logger.warning("profile_load_failed_for_path", error=str(e))
    record_agent_step(
        task,
        agent_key="profile_context",
        label="画像分析智能体",
        status="completed",
        summary="已加载八维学习画像并提炼路径规划约束。" if profile_context else "当前无有效画像，使用目标信息规划路径。",
        artifact_type="个性化约束",
    )

    user_message = f"""请为以下学习目标规划学习路径：

学习目标：{goal.title}
核心主题：{topic}
{f"目标描述：{goal.raw_description}" if goal.raw_description else ""}
{f"当前水平：{goal.current_level}" if goal.current_level else ""}
{f"目标水平：{goal.target_level}" if goal.target_level else ""}
{profile_context}

请生成 5-15 个学习节点，确保：
- 节点标题以核心主题「{topic}」为基础，不要包含用户目标的完整表述
- 标题具体明确（例如："{topic} — 指针与引用"而非"{topic}基础"）
- 每个节点 estimated_minutes 在 20-60 之间
- difficulty 按照节点顺序递增
- edges 反映真实的前置依赖关系
- 如果学习者画像显示知识基础较弱，适当增加基础节点；如果先修知识掌握较好，可以减少前置复习节点
- 如果学习者画像显示学习节奏偏慢，适当增加 estimated_minutes；偏快则可以压缩"""

    # Try LLM generation, fall back to template if LLM unavailable
    stages = []
    nodes = []
    edges = []
    summary = f"学习路径: {goal.title}"

    record_agent_step(
        task,
        agent_key="path_planner",
        label="路径规划智能体",
        status="running",
        summary="正在结合学习目标、当前水平和画像生成 DAG 学习路径。",
        artifact_type="路径草案",
    )
    await update_task_status(
        db, task.id, "running", progress=30, stage="generating", message="智能体正在调用大语言模型生成路径..."
    )
    path_generation_source = "llm"
    try:
        result = await llm_json(system_prompt, user_message, temperature=0.5, max_tokens=4096)

        stages = result.get("stages", [])
        nodes = result.get("nodes", [])
        edges = result.get("edges", [])
        summary = result.get("summary", summary)

        # Validate: must have 5-15 nodes
        if len(nodes) < 5:
            raise LLMError(f"Too few nodes: {len(nodes)}")
        if len(nodes) > 15:
            nodes = nodes[:15]

        await update_task_status(
            db,
            task.id,
            "running",
            progress=60,
            stage="generating",
            message=f"智能体已生成 {len(nodes)} 个学习节点，正在校验...",
        )
    except Exception as e:
        # Fallback: template-based generation with goal-aware titles
        logger.warning("llm_path_fallback", error_type=type(e).__name__, error=str(e), exc_info=True)
        await update_task_status(
            db, task.id, "running", progress=35, stage="generating", message="LLM 不可用，使用模板生成路径..."
        )
        topic = _extract_topic(goal.title)
        path_generation_source = "fallback"
        stages = [
            {
                "title": f"{topic} — 基础入门",
                "description": f"掌握{topic}的核心基础概念",
                "stage_order": 1,
                "outcome": f"理解{topic}的基本原理",
            },
            {
                "title": f"{topic} — 核心技能",
                "description": f"深入学习{topic}的关键技术",
                "stage_order": 2,
                "outcome": f"掌握{topic}的核心应用",
            },
            {
                "title": f"{topic} — 综合实践",
                "description": f"通过项目实践巩固{topic}知识",
                "stage_order": 3,
                "outcome": f"能够独立运用{topic}解决问题",
            },
        ]
        nodes = [
            {
                "node_id": "node-1",
                "title": f"{topic}概述与发展背景",
                "description": f"了解{topic}的定义、应用场景和发展历史",
                "node_order": 1,
                "level": 1,
                "difficulty": "beginner",
                "estimated_minutes": 25,
                "stage_id": "stage-1",
                "learning_outcomes": [f"理解{topic}的基本定义", f"了解{topic}的典型应用场景"],
            },
            {
                "node_id": "node-2",
                "title": f"{topic}的核心概念与术语",
                "description": f"学习{topic}中的关键概念、专业术语和基础理论",
                "node_order": 2,
                "level": 1,
                "difficulty": "beginner",
                "estimated_minutes": 35,
                "stage_id": "stage-1",
                "learning_outcomes": [f"掌握{topic}的核心术语", "理解基础理论框架"],
            },
            {
                "node_id": "node-3",
                "title": f"{topic}的基本操作与工具",
                "description": f"学习使用{topic}相关的基本工具和操作方法",
                "node_order": 3,
                "level": 2,
                "difficulty": "beginner",
                "estimated_minutes": 40,
                "stage_id": "stage-1",
                "learning_outcomes": ["能够使用基本工具完成简单任务", "熟悉常用操作流程"],
            },
            {
                "node_id": "node-4",
                "title": f"{topic}的关键技术原理",
                "description": f"深入理解{topic}背后的技术原理和工作机制",
                "node_order": 4,
                "level": 2,
                "difficulty": "intermediate",
                "estimated_minutes": 45,
                "stage_id": "stage-2",
                "learning_outcomes": ["理解核心技术原理", "能够分析技术优缺点"],
            },
            {
                "node_id": "node-5",
                "title": f"{topic}的常见模式与最佳实践",
                "description": f"学习{topic}中的常见设计模式和行业最佳实践",
                "node_order": 5,
                "level": 2,
                "difficulty": "intermediate",
                "estimated_minutes": 40,
                "stage_id": "stage-2",
                "learning_outcomes": ["掌握常见设计模式", "了解行业最佳实践"],
            },
            {
                "node_id": "node-6",
                "title": f"{topic}的进阶技巧与性能优化",
                "description": f"学习{topic}的高级用法和性能优化策略",
                "node_order": 6,
                "level": 3,
                "difficulty": "intermediate",
                "estimated_minutes": 50,
                "stage_id": "stage-2",
                "learning_outcomes": ["掌握进阶使用技巧", "能够进行基本的性能优化"],
            },
            {
                "node_id": "node-7",
                "title": f"{topic}的错误处理与调试",
                "description": f"学习如何诊断和解决{topic}中的常见问题",
                "node_order": 7,
                "level": 3,
                "difficulty": "intermediate",
                "estimated_minutes": 35,
                "stage_id": "stage-2",
                "learning_outcomes": ["能够独立排查常见错误", "掌握调试工具和方法"],
            },
            {
                "node_id": "node-8",
                "title": f"{topic}的项目实战应用",
                "description": f"通过实际项目案例综合运用{topic}所学知识",
                "node_order": 8,
                "level": 3,
                "difficulty": "advanced",
                "estimated_minutes": 55,
                "stage_id": "stage-3",
                "learning_outcomes": ["能够独立完成项目实践", "综合运用所学知识解决实际问题"],
            },
            {
                "node_id": "node-9",
                "title": f"{topic}的扩展与生态",
                "description": f"了解{topic}相关的扩展工具、社区资源和生态系统",
                "node_order": 9,
                "level": 3,
                "difficulty": "advanced",
                "estimated_minutes": 30,
                "stage_id": "stage-3",
                "learning_outcomes": ["了解相关工具和框架", "能够选择合适的技术栈"],
            },
            {
                "node_id": "node-10",
                "title": f"{topic}总结与持续学习路径",
                "description": f"总结{topic}的学习要点，规划后续进阶方向",
                "node_order": 10,
                "level": 3,
                "difficulty": "advanced",
                "estimated_minutes": 25,
                "stage_id": "stage-3",
                "learning_outcomes": ["系统回顾核心知识点", "明确后续学习方向"],
            },
        ]
        edges = [{"source_node_id": f"node-{i}", "target_node_id": f"node-{i + 1}"} for i in range(1, 10)]

    record_agent_step(
        task,
        agent_key="path_planner",
        label="路径规划智能体",
        status="completed",
        summary=f"已通过 {path_generation_source} 生成 {len(nodes)} 个节点和 {len(edges)} 条依赖关系。",
        artifact_type="DAG 学习路径",
    )
    record_agent_step(
        task,
        agent_key="path_validator",
        label="路径结构校验器",
        status="running",
        summary="正在检查节点数量、依赖关系和路径结构。",
        artifact_type="校验报告",
    )
    await asyncio.sleep(1)
    await update_task_status(db, task.id, "running", progress=75, stage="validating", message="正在校验学习路径结构...")

    path_service = PathService(db)

    from app.models.path import LearningPath

    path = LearningPath(
        id=str(uuid.uuid4()),
        user_id=user_id,
        goal_id=goal_id,
        status="draft",
    )
    db.add(path)
    await db.flush()

    await asyncio.sleep(1)
    await update_task_status(db, task.id, "running", progress=90, stage="finalizing", message="正在写入学习路径...")

    version = await path_service.create_path_version(
        path_id=path.id,
        user_id=user_id,
        stages=stages,
        nodes=nodes,
        edges=edges,
        summary=summary,
    )
    record_agent_step(
        task,
        agent_key="path_validator",
        label="路径结构校验器",
        status="completed",
        summary="DAG 结构校验通过，已生成可审核的路径版本。",
        artifact_type="路径版本",
    )

    goal.current_path_id = path.id

    # Transition goal from "planning" to "ready" so resume service picks it up
    # transition_goal commits the session, persisting current_path_id as well
    await goal_service.transition_goal(goal_id, user_id, "ready")

    # Don't call update_task_status here — the caller (execute_background_task)
    # will mark the task as "completed" with the result payload.
    await db.flush()

    return {"path_id": path.id, "version": version.version_number}


@register_handler("learning_unit_generation")
async def _execute_unit_generation(db: Any, task: Any) -> dict[str, Any]:
    """Execute a unit content generation task using two-phase transaction.

    Transaction A (short, committed):
      - Load node/goal context
      - Mark version as generating
      - Commit (release locks before LLM)

    LLM call (no DB transaction):
      - Generate structured content
      - Validate structure
      - Review quality

    Transaction B (short, committed via new session):
      - SELECT version FOR UPDATE
      - Check task not cancelled
      - Save content and atomically switch active version
      - On failure: mark version failed, keep old active version
    """
    import json

    from sqlalchemy import select

    from app.models.goal import LearningGoal
    from app.models.path import LearningNode, LearningPath
    from app.models.unit import LearningUnitContentVersion
    from app.services.llm import LLMError, llm_json

    node_id = task.target_id
    metadata = task.target_metadata or {}
    path_id = metadata.get("path_id", "")
    preferences = metadata.get("preferences", "")
    version_id = metadata.get("unit_content_version_id", "")

    # ------------------------------------------------
    # Transaction A: load context, mark version generating
    # ------------------------------------------------
    await update_task_status(db, task.id, "running", progress=5, stage="analyzing", message="正在分析节点上下文...")

    node_result = await db.execute(select(LearningNode).where(LearningNode.id == node_id))
    node = node_result.scalar_one_or_none()
    node_title = node.title if node else "未知节点"
    node_desc = node.description if node else ""
    node_difficulty = node.difficulty if node else "beginner"
    outcomes_raw = node.learning_outcomes if node else "[]"
    learning_outcomes = json.loads(outcomes_raw) if isinstance(outcomes_raw, str) else (outcomes_raw or [])

    # Look up goal context
    goal_title = ""
    if path_id:
        path_result = await db.execute(select(LearningPath).where(LearningPath.id == path_id))
        path = path_result.scalar_one_or_none()
        if path and path.goal_id:
            goal_result = await db.execute(select(LearningGoal).where(LearningGoal.id == path.goal_id))
            goal = goal_result.scalar_one_or_none()
            if goal:
                goal_title = goal.title or ""

    # Load the version and mark it generating
    version: LearningUnitContentVersion | None = None
    if version_id:
        version_result = await db.execute(
            select(LearningUnitContentVersion).where(LearningUnitContentVersion.id == version_id)
        )
        version = version_result.scalar_one_or_none()
        if version:
            version.status = "generating"

    # Commit Transaction A — release all locks before LLM call
    await db.commit()

    objectives = (
        learning_outcomes
        if learning_outcomes
        else [
            f"理解{node_title}的核心概念",
            f"掌握{node_title}的基本应用",
        ]
    )

    # Phase 3.6-D: Load student profile for personalised content generation
    profile_context = ""
    try:
        from app.services.profile_merge import load_profile_context

        _profile, profile_context = await load_profile_context(db, task.user_id)
    except Exception as e:
        logger.warning("profile_load_failed_for_unit", error=str(e))
    record_agent_step(
        task,
        agent_key="profile_context",
        label="画像分析智能体",
        status="completed",
        summary="已提取内容深度、讲解方式和示例偏好。" if profile_context else "未发现有效画像，采用节点默认教学策略。",
        artifact_type="内容个性化约束",
    )

    # ------------------------------------------------
    # LLM call (no DB transaction)
    # ------------------------------------------------
    content_data = None
    generation_source = "llm"
    record_agent_step(
        task,
        agent_key="content_generator",
        label="课程内容生成智能体",
        status="running",
        summary="正在生成讲义结构、案例、代码、易错点和实践项目。",
        artifact_type="课程内容",
    )
    await update_task_status(
        db, task.id, "running", progress=25, stage="generating", message="智能体正在调用大语言模型生成内容..."
    )
    try:
        from app.prompts.agents import CONTENT_GENERATOR_SYSTEM, content_generator_user

        system_prompt = CONTENT_GENERATOR_SYSTEM
        user_msg = content_generator_user(node_title, node_desc, node_difficulty, objectives, goal_title)
        if preferences:
            user_msg += f"\n\n用户个性化偏好（请务必参考）：\n{preferences}"
        if profile_context:
            user_msg += f"\n\n{profile_context}\n请根据以上画像信息调整内容深度、讲解方式和示例类型。"

        content_data = await llm_json(system_prompt, user_msg, temperature=0.6, max_tokens=12000)

        if not content_data.get("sections") or len(content_data["sections"]) < 2:
            raise LLMError("Insufficient sections generated")

        await update_task_status(
            db, task.id, "running", progress=80, stage="finalizing", message="智能体已完成内容生成，正在整理..."
        )

    except Exception as e:
        logger.warning("llm_unit_fallback", error_type=type(e).__name__, error=str(e), exc_info=True)
        await update_task_status(
            db, task.id, "running", progress=30, stage="generating", message="LLM 不可用，使用模板生成内容..."
        )

    # Fallback: template-based content
    if content_data is None:
        content_data = _build_fallback_content(node_title, node_desc, node_difficulty, objectives)
        generation_source = "fallback"

    content_data, quality_report = _normalize_learning_material(
        content_data,
        node_title=node_title,
        node_difficulty=node_difficulty,
        objectives=objectives,
    )
    if quality_report["score"] < 55 and generation_source == "llm":
        logger.warning(
            "llm_unit_quality_fallback",
            node_id=node_id,
            score=quality_report["score"],
            issues=quality_report["issues"],
        )
        content_data, fallback_report = _normalize_learning_material(
            _build_fallback_content(node_title, node_desc, node_difficulty, objectives),
            node_title=node_title,
            node_difficulty=node_difficulty,
            objectives=objectives,
        )
        fallback_report["replaced_llm_score"] = quality_report["score"]
        quality_report = fallback_report
        generation_source = "fallback_quality_gate"

    content_data["generation_metadata"] = {
        "source": generation_source,
        "quality_report": quality_report,
    }
    record_agent_step(
        task,
        agent_key="content_generator",
        label="课程内容生成智能体",
        status="completed",
        summary=f"内容生成完成，来源为 {generation_source}，规则质量分 {quality_report['score']}。",
        artifact_type="结构化课程内容",
    )
    record_agent_step(
        task,
        agent_key="quality_gate",
        label="教学质量校验器",
        status="completed",
        summary=f"完成结构、深度、示例和占位内容检查，质量分 {quality_report['score']}。",
        artifact_type="质量报告",
    )

    # Review step
    review_passed = True
    try:
        record_agent_step(
            task,
            agent_key="content_reviewer",
            label="内容审核智能体",
            status="running",
            summary="正在审核事实准确性、逻辑完整性、代码质量和目标覆盖。",
            artifact_type="审核意见",
        )
        await update_task_status(
            db, task.id, "running", progress=85, stage="reviewing", message="智能体正在审核内容质量..."
        )
        from app.prompts.agents import REVIEWER_SYSTEM, reviewer_user

        sections_for_review = content_data.get("sections", [])
        review_result = await llm_json(
            REVIEWER_SYSTEM,
            reviewer_user(node_title, sections_for_review),
            temperature=0.2,
            max_tokens=1024,
        )
        review_passed = review_result.get("passed", True)
        content_data["generation_metadata"].update(
            {
                "reviewed": True,
                "review_score": review_result.get("score", 0),
                "review_issues": review_result.get("issues", []),
                "review_summary": review_result.get("summary", ""),
            }
        )
        if not review_passed:
            logger.warning("content_review_failed", node_id=node_id, issues=review_result.get("issues", []))
            record_agent_step(
                task,
                agent_key="content_reviewer",
                label="内容审核智能体",
                status="needs_revision",
                summary=f"首轮审核未通过，发现 {len(review_result.get('issues', []))} 个待修问题。",
                artifact_type="返修清单",
            )
            await update_task_status(
                db, task.id, "running", progress=87, stage="revising", message="审核未通过，内容智能体正在返修..."
            )

            from app.prompts.agents import CONTENT_GENERATOR_SYSTEM, content_revision_user

            record_agent_step(
                task,
                agent_key="content_generator",
                label="课程内容生成智能体",
                status="running",
                summary="正在根据审核问题进行一次定向返修。",
                iteration=2,
                artifact_type="返修课程内容",
            )
            revised_raw = await llm_json(
                CONTENT_GENERATOR_SYSTEM,
                content_revision_user(node_title, content_data, review_result.get("issues", [])),
                temperature=0.35,
                max_tokens=12000,
            )
            if not revised_raw.get("sections") or len(revised_raw["sections"]) < 2:
                raise LLMError("Revision returned insufficient sections")
            revised_content, revised_quality = _normalize_learning_material(
                revised_raw,
                node_title=node_title,
                node_difficulty=node_difficulty,
                objectives=objectives,
            )
            revised_content["generation_metadata"] = {
                "source": "llm_revision",
                "quality_report": revised_quality,
                "revision_iteration": 1,
                "previous_review_issues": review_result.get("issues", []),
            }
            content_data = revised_content
            record_agent_step(
                task,
                agent_key="content_generator",
                label="课程内容生成智能体",
                status="completed",
                summary=f"定向返修完成，返修后规则质量分 {revised_quality['score']}。",
                iteration=2,
                artifact_type="返修课程内容",
            )
            record_agent_step(
                task,
                agent_key="content_reviewer",
                label="内容审核智能体",
                status="running",
                summary="正在复审返修后的课程内容。",
                iteration=2,
                artifact_type="复审意见",
            )
            await update_task_status(
                db, task.id, "running", progress=89, stage="reviewing", message="内容返修完成，正在复审..."
            )
            second_review = await llm_json(
                REVIEWER_SYSTEM,
                reviewer_user(node_title, content_data.get("sections", [])),
                temperature=0.2,
                max_tokens=1024,
            )
            review_passed = second_review.get("passed", True)
            content_data["generation_metadata"].update(
                {
                    "reviewed": True,
                    "review_score": second_review.get("score", 0),
                    "review_issues": second_review.get("issues", []),
                    "review_summary": second_review.get("summary", ""),
                    "review_iterations": 2,
                }
            )
            record_agent_step(
                task,
                agent_key="content_reviewer",
                label="内容审核智能体",
                status="completed" if review_passed else "failed",
                summary=(
                    f"复审通过，审核分 {second_review.get('score', 0)}。"
                    if review_passed
                    else f"复审仍有 {len(second_review.get('issues', []))} 个问题，已保留风险标记。"
                ),
                iteration=2,
                artifact_type="最终审核报告",
            )
        else:
            record_agent_step(
                task,
                agent_key="content_reviewer",
                label="内容审核智能体",
                status="completed",
                summary=f"首轮审核通过，审核分 {review_result.get('score', 0)}。",
                artifact_type="审核报告",
            )
    except Exception as e:
        logger.warning("review_step_error", error=str(e))
        record_agent_step(
            task,
            agent_key="content_reviewer" if review_passed else "content_generator",
            label="内容审核智能体" if review_passed else "课程内容生成智能体",
            status="failed",
            summary=f"审核或返修过程异常，已保留质量门禁结果：{type(e).__name__}。",
            iteration=1 if review_passed else 2,
            artifact_type="异常记录",
        )

    await update_task_status(db, task.id, "running", progress=90, stage="finalizing", message="正在保存学习内容...")

    # ------------------------------------------------
    # Transaction B: atomic version switch (same session, new transaction)
    #    The session was released by commit() above, so with_for_update()
    #    will acquire a fresh lock.
    # ------------------------------------------------
    try:
        result = await _complete_unit_generation(db, version_id, content_data, task.id)
        unit_id = result["unit_id"]
    except Exception:
        logger.exception("unit_generation_txn_b_failed", node_id=node_id, version_id=version_id)
        await _fail_unit_generation(db, version_id)
        raise

    await update_task_status(db, task.id, "running", progress=100, stage="completed", message="单元内容生成完成")
    return {"path_id": path_id, "unit_id": unit_id, "node_id": node_id}


async def _complete_unit_generation(
    txn_db: Any,
    version_id: str,
    content_data: dict[str, Any],
    task_id: str,
) -> dict[str, str]:
    """Transaction B: atomically save generated content and switch versions."""
    from sqlalchemy import select

    from app.common.datetime import utc_now
    from app.models.unit import LearningUnitContent, LearningUnitContentVersion

    # Load version FOR UPDATE to prevent concurrent completion
    version_result = await txn_db.execute(
        select(LearningUnitContentVersion).where(LearningUnitContentVersion.id == version_id).with_for_update()
    )
    version: LearningUnitContentVersion | None = version_result.scalar_one_or_none()
    if not version:
        raise ValueError(f"Version {version_id} not found")

    # Check task was not cancelled mid-flight
    from app.common.enums import TaskStatus
    from app.models.task import BackgroundTask

    task_result = await txn_db.execute(select(BackgroundTask).where(BackgroundTask.id == task_id))
    bg_task = task_result.scalar_one_or_none()
    if bg_task and bg_task.status == TaskStatus.CANCELLED.value:
        # Task was cancelled — don't activate this version
        version.status = "failed"
        version.error_code = "TASK_CANCELLED"
        version.error_message = "Task was cancelled before completion"
        await txn_db.commit()
        raise RuntimeError("Task was cancelled")

    # Save content to version
    version.status = "ready"
    version.content = content_data
    version.completed_at = utc_now()

    # Load unit content and atomically switch active version
    uc_result = await txn_db.execute(
        select(LearningUnitContent).where(LearningUnitContent.id == version.unit_content_id).with_for_update()
    )
    uc: LearningUnitContent | None = uc_result.scalar_one_or_none()
    if uc:
        # Mark old active version as superseded
        if uc.active_version_id:
            old_version_result = await txn_db.execute(
                select(LearningUnitContentVersion).where(LearningUnitContentVersion.id == uc.active_version_id)
            )
            old_version = old_version_result.scalar_one_or_none()
            if old_version and old_version.id != version.id:
                old_version.status = "superseded"

        # Atomically switch
        uc.active_version_id = version.id
        version.activated_at = utc_now()
        uc.status = "ready"
        uc.active_task_id = None

        # Lectures are derived from the active unit version. Clear the old
        # lecture so the client rebuilds it from the newly activated source.
        from app.models.unit import LearningLecture

        lecture_result = await txn_db.execute(
            select(LearningLecture).where(
                LearningLecture.user_id == uc.user_id,
                LearningLecture.path_id == uc.path_id,
                LearningLecture.node_id == uc.node_id,
            )
        )
        lecture = lecture_result.scalar_one_or_none()
        if lecture:
            lecture.status = "not_generated"
            lecture.content = None
            lecture.active_task_id = None

    await txn_db.commit()
    return {"unit_id": uc.id if uc else version.unit_content_id}


async def _fail_unit_generation(txn_db: Any, version_id: str) -> None:
    """Mark a version as failed without affecting the active version."""
    from sqlalchemy import select

    from app.models.unit import LearningUnitContent, LearningUnitContentVersion

    try:
        version_result = await txn_db.execute(
            select(LearningUnitContentVersion).where(LearningUnitContentVersion.id == version_id).with_for_update()
        )
        version = version_result.scalar_one_or_none()
        if version and version.status == "generating":
            version.status = "failed"

            # Reset unit content to ready (old version still active)
            uc_result = await txn_db.execute(
                select(LearningUnitContent).where(LearningUnitContent.id == version.unit_content_id).with_for_update()
            )
            uc = uc_result.scalar_one_or_none()
            if uc and uc.active_task_id:
                uc.status = "ready" if uc.active_version_id else "failed"
                uc.active_task_id = None

            await txn_db.commit()
    except Exception:
        logger.exception("failed_to_mark_version_failed", version_id=version_id)
        await txn_db.rollback()


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _normalize_learning_material(
    content: dict[str, Any],
    *,
    node_title: str,
    node_difficulty: str,
    objectives: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Normalize generated JSON into the canonical learning-material structure."""
    normalized = dict(content)
    normalized["difficulty"] = node_difficulty
    normalized["introduction"] = str(content.get("introduction") or f"# {node_title}")
    normalized["prerequisites"] = _string_list(content.get("prerequisites"))
    normalized["objectives"] = _string_list(content.get("objectives")) or objectives
    normalized["completion_criteria"] = (
        _string_list(content.get("completion_criteria")) or normalized["objectives"]
    )

    raw_sections = content.get("sections")
    sections_list: list[Any] = raw_sections if isinstance(raw_sections, list) else []
    sections: list[dict[str, Any]] = []
    for index, raw in enumerate(sections_list):
        if not isinstance(raw, dict):
            continue
        section = dict(raw)
        section_id = str(raw.get("section_id") or f"sec-{index + 1}")
        title = str(raw.get("title") or f"章节 {index + 1}")
        section_content = str(raw.get("content") or "")
        concepts = _string_list(raw.get("concepts")) or _string_list(raw.get("mind_map_nodes")) or [title]
        checkpoints = _string_list(raw.get("checkpoints"))
        if not checkpoints:
            checkpoints = [f"你能否用自己的话解释「{concepts[0]}」？"]
        section.update(
            {
                "section_id": section_id,
                "title": title,
                "content": section_content,
                "order": index + 1,
                "concepts": concepts[:6],
                "examples": raw.get("examples") if isinstance(raw.get("examples"), list) else [],
                "code_examples": (
                    raw.get("code_examples") if isinstance(raw.get("code_examples"), list) else []
                ),
                "common_mistakes": (
                    raw.get("common_mistakes") if isinstance(raw.get("common_mistakes"), list) else []
                ),
                "checkpoints": checkpoints[:4],
                "mind_map_nodes": (_string_list(raw.get("mind_map_nodes")) or concepts)[:8],
            }
        )
        sections.append(section)
    normalized["sections"] = sections

    practice_tasks_raw = content.get("practice_tasks")
    practice_tasks: list[Any] = practice_tasks_raw if isinstance(practice_tasks_raw, list) else []
    normalized["practice_tasks"] = practice_tasks
    estimated = content.get("estimated_minutes")
    normalized["estimated_minutes"] = (
        max(20, min(120, int(estimated)))
        if isinstance(estimated, (int, float))
        else max(20, min(90, len(sections) * 12))
    )
    project = content.get("project") if isinstance(content.get("project"), dict) else {}
    if not project:
        project = {
            "title": f"综合实践：{node_title}",
            "description": f"综合运用本单元知识完成一个关于「{node_title}」的可验证成果。",
            "steps": [
                str(task.get("description") or task.get("title"))
                for task in practice_tasks[:4]
                if isinstance(task, dict)
            ],
            "deliverables": ["可运行结果或书面解答", "关键步骤说明"],
        }
    normalized["project"] = project
    normalized["summary"] = str(content.get("summary") or f"完成了「{node_title}」的系统学习。")
    normalized["references"] = content.get("references") if isinstance(content.get("references"), list) else []

    combined_content = "\n".join(section["content"] for section in sections)
    structured_sections = sum(
        1
        for section in sections
        if section["concepts"] and section["checkpoints"]
    )
    generic_phrases = ("内部机制和数据流动方式", "处理完成", "有广泛的应用场景", "确保理解前置概念")
    generic_hits = sum(combined_content.count(phrase) for phrase in generic_phrases)
    code_blocks = combined_content.count("```") // 2
    score = min(25, len(sections) * 6)
    score += min(30, len(combined_content) // 80)
    score += min(15, code_blocks * 5)
    score += min(20, structured_sections * 5)
    score += 10 if len(practice_tasks) >= 3 else len(practice_tasks) * 3
    score = max(0, min(100, score - generic_hits * 12))
    issues: list[str] = []
    if len(sections) < 4:
        issues.append("章节少于 4 个")
    if len(combined_content) < 1600:
        issues.append("正文深度不足")
    if code_blocks == 0 and "代码" in node_title:
        issues.append("缺少可运行代码示例")
    if generic_hits:
        issues.append("包含通用占位描述")
    quality_report = {
        "score": score,
        "passed": score >= 70,
        "issues": issues,
        "section_count": len(sections),
        "character_count": len(combined_content),
        "code_example_count": code_blocks,
        "structured_section_count": structured_sections,
        "generic_phrase_hits": generic_hits,
    }
    return normalized, quality_report


def _build_fallback_content(
    node_title: str,
    node_desc: str | None,
    node_difficulty: str,
    objectives: list[str],
) -> dict[str, Any]:
    """Build template-based fallback content when LLM is unavailable."""
    normalized_title = node_title.lower()
    if "python" in normalized_title and ("语法" in node_title or "环境" in node_title):
        return _build_python_basics_fallback(node_title, node_desc, objectives)
    if "python" in normalized_title and any(keyword in node_title for keyword in ("概述", "背景", "历史")):
        return _build_python_overview_fallback(node_title, node_desc, objectives)
    if "python" in normalized_title:
        return _build_python_topic_fallback(node_title, node_desc, node_difficulty, objectives)

    diff_map = {"beginner": "入门", "intermediate": "进阶", "advanced": "高级"}
    difficulty_label = diff_map.get(node_difficulty, "基础")
    node_desc_fallback = node_desc or f"本单元将系统学习{node_title}的理论基础与实践应用。"

    intro = f"# {node_title}\n\n{node_desc_fallback}"

    sec1_content = (
        f"## 概念介绍\n\n"
        f"{node_desc or f'{node_title}是本学习路径中的一个重要知识点。'}\n\n"
        f"本节将从{difficulty_label}角度出发，"
        f"帮助你建立对{node_title}的整体认知。\n\n### 学习目标\n\n"
    ) + "\n".join(f"- {o}" for o in objectives)

    sec2_content = (
        f"## 核心原理\n\n要深入理解{node_title}，需要掌握以下关键点：\n\n"
        f"1. **基本定义**：{node_title}的基本定义和适用场景\n"
        f"2. **工作原理**：内部机制和数据流动方式\n"
        f"3. **关键特性**：区别于其他概念的核心特征\n\n"
        f"> 💡 建议结合实际案例来理解这些概念。"
    )

    sec3_content = (
        f"## 实际应用\n\n{node_title}在实际开发中有广泛的应用场景。\n\n"
        f"### 代码示例\n\n```python\n"
        f"# {node_title} 基本示例\ndef main():\n"
        f"    result = process()\n    return result\n\n"
        f"def process():\n    return '处理完成'\n\n"
        f"if __name__ == '__main__':\n    print(main())\n```\n\n"
        f"### 注意事项\n\n1. 确保理解前置概念\n"
        f"2. 注意边界条件的处理\n3. 考虑性能和可扩展性"
    )

    sec4_content = (
        f"## 常见问题与最佳实践\n\n### 最佳实践\n\n"
        f"- ✅ 先理解概念，再动手实践\n"
        f"- ✅ 多做练习，加深理解\n"
        f"- ✅ 阅读优秀项目中的实际应用\n\n"
        f"### 进阶方向\n\n"
        f"掌握{node_title}的基础后，可以进一步探索高级用法和性能优化技巧。"
    )

    return {
        "introduction": intro,
        "objectives": objectives,
        "sections": [
            {"section_id": "sec-1", "title": f"什么是{node_title}？", "content": sec1_content, "order": 1},
            {"section_id": "sec-2", "title": f"{node_title}的核心原理", "content": sec2_content, "order": 2},
            {"section_id": "sec-3", "title": f"{node_title}的实际应用", "content": sec3_content, "order": 3},
            {"section_id": "sec-4", "title": "常见问题与最佳实践", "content": sec4_content, "order": 4},
        ],
        "practice_tasks": [
            {
                "task_id": f"pt-{i + 1}",
                "title": f"练习{i + 1}：{node_title}基础操作",
                "description": f"尝试使用{node_title}完成一个简单的任务。",
                "difficulty": node_difficulty,
            }
            for i in range(3)
        ],
        "summary": f"本单元系统地介绍了{node_title}的核心概念和实际应用。建议完成练习后再进行通关评估。",
        "references": [{"title": f"{node_title} 官方文档", "url": None, "type": "documentation"}],
    }


def _build_python_basics_fallback(
    node_title: str,
    node_desc: str | None,
    objectives: list[str],
) -> dict[str, Any]:
    """Provide a useful offline lesson for Python environment and syntax nodes."""
    introduction = (
        f"# {node_title}\n\n"
        f"{node_desc or '从安装与运行开始，掌握变量、基本类型以及控制台输入输出。'}"
        "本节所有示例都可以直接保存为 `.py` 文件运行。"
    )
    setup_content = """## 1. 安装并验证 Python

从 [Python 官网](https://www.python.org/downloads/) 安装 Python。Windows 安装时勾选 **Add Python to PATH**。完成后打开终端执行：

```bash
python --version
```

Windows 也可以执行 `py --version`。只要能看到版本号，就说明解释器可用。

推荐使用 VS Code，并安装官方 Python 扩展。新建 `hello.py`：

```python
print("Hello, Python!")
```

在文件目录运行 `python hello.py`。看到输出即完成环境验证。"""
    types_content = """## 2. 变量与动态类型

Python 变量不需要预先声明类型，赋值时会绑定到一个对象：

```python
name = "小明"       # str：字符串
age = 18            # int：整数
height = 1.72       # float：小数
is_student = True   # bool：布尔值

print(type(name))
print(type(age))
```

同一个变量可以重新绑定到不同类型，但实际项目中应保持含义稳定，避免降低可读性：

```python
value = 10
value = "ten"  # 合法，但不推荐在同一业务含义中这样写
```"""
    io_content = """## 3. 使用 `print()` 与 `input()`

`print()` 把内容输出到控制台；`input()` 显示提示并读取用户输入。注意：`input()` 的结果始终是字符串。

```python
name = input("请输入姓名：")
age_text = input("请输入年龄：")
age = int(age_text)

print("你好，", name)
print(f"明年你将 {age + 1} 岁")
```

如果用户输入的年龄不是数字，`int()` 会报错。入门阶段先输入有效数字，后续学习异常处理时再完善校验。"""
    practice_content = """## 4. 完整练习：个人信息卡

把下面代码保存为 `profile.py` 并运行：

```python
name = input("姓名：")
age = int(input("年龄："))
city = input("所在城市：")
likes_python = input("喜欢 Python 吗（yes/no）：") == "yes"

print("--- 个人信息卡 ---")
print(f"姓名：{name}")
print(f"年龄：{age}")
print(f"城市：{city}")
print(f"喜欢 Python：{likes_python}")
```

检查你是否能解释每个变量的类型，以及为什么比较表达式会得到布尔值。"""

    return {
        "introduction": introduction,
        "prerequisites": ["会使用文件管理器和终端的基本操作"],
        "objectives": objectives,
        "estimated_minutes": 55,
        "completion_criteria": [
            "能够在终端运行一个 .py 文件",
            "能够解释 int、float、str 和 bool 的区别",
            "能够使用 print() 与 input() 完成简单交互",
        ],
        "sections": [
            {
                "section_id": "sec-1",
                "title": "安装、编辑器与首次运行",
                "content": setup_content,
                "order": 1,
                "concepts": ["Python 解释器", "PATH 环境变量", "Python 脚本"],
                "examples": [{"title": "Hello Python", "description": "运行第一个 hello.py 文件"}],
                "code_examples": [
                    {
                        "title": "首次运行",
                        "language": "python",
                        "code": 'print("Hello, Python!")',
                        "explanation": "使用 print() 向终端输出文本。",
                    }
                ],
                "common_mistakes": [
                    {"mistake": "终端找不到 python", "correction": "检查 PATH，Windows 可先尝试 py 命令。"}
                ],
                "checkpoints": ["python --version 输出代表什么？", "如何运行 hello.py？"],
                "mind_map_nodes": ["安装解释器", "验证版本", "运行 .py 文件"],
            },
            {
                "section_id": "sec-2",
                "title": "变量和基本数据类型",
                "content": types_content,
                "order": 2,
                "concepts": ["变量绑定", "动态类型", "int", "float", "str", "bool"],
                "examples": [{"title": "个人属性变量", "description": "使用四种基本类型描述个人信息"}],
                "code_examples": [],
                "common_mistakes": [
                    {"mistake": "频繁改变同一变量的含义", "correction": "变量名称和类型应保持业务含义稳定。"}
                ],
                "checkpoints": ["type() 有什么作用？", "True 和 \"True\" 有什么区别？"],
                "mind_map_nodes": ["变量赋值", "动态类型", "四种基本类型"],
            },
            {
                "section_id": "sec-3",
                "title": "控制台输入与输出",
                "content": io_content,
                "order": 3,
                "concepts": ["print()", "input()", "字符串转换", "f-string"],
                "examples": [{"title": "年龄交互", "description": "读取年龄并计算下一年的年龄"}],
                "code_examples": [],
                "common_mistakes": [
                    {"mistake": "直接用 input() 结果做加法", "correction": "input() 返回字符串，应先用 int() 转换。"}
                ],
                "checkpoints": ["input() 返回什么类型？", "何时需要 int()？"],
                "mind_map_nodes": ["控制台输出", "读取用户输入", "类型转换", "格式化字符串"],
            },
            {
                "section_id": "sec-4",
                "title": "动手完成个人信息卡",
                "content": practice_content,
                "order": 4,
                "concepts": ["需求拆解", "数据采集", "格式化输出", "布尔表达式"],
                "examples": [{"title": "个人信息卡", "description": "组合本节知识完成可运行小程序"}],
                "code_examples": [],
                "common_mistakes": [],
                "checkpoints": ["程序使用了哪些数据类型？", "如何验证输出正确？"],
                "mind_map_nodes": ["采集姓名年龄", "布尔比较", "输出信息卡"],
            },
        ],
        "project": {
            "title": "命令行个人信息卡",
            "description": "编写一个能收集、转换并格式化展示个人资料的 Python 脚本。",
            "steps": ["创建 profile.py", "读取姓名、年龄和城市", "完成类型转换", "格式化输出", "运行验证"],
            "deliverables": ["可运行的 profile.py", "一次完整运行结果", "变量类型说明"],
        },
        "practice_tasks": [
            {
                "task_id": "pt-1",
                "title": "运行第一个 Python 脚本",
                "description": "创建 hello.py，输出 Python 版本之外的自定义欢迎语。",
                "difficulty": "beginner",
            },
            {
                "task_id": "pt-2",
                "title": "观察变量类型",
                "description": "声明数字、字符串和布尔变量，并用 type() 输出它们的类型。",
                "difficulty": "beginner",
            },
            {
                "task_id": "pt-3",
                "title": "制作个人信息卡",
                "description": "使用 input() 收集姓名和年龄，再通过 f-string 输出格式化结果。",
                "difficulty": "beginner",
            },
        ],
        "summary": "你已经完成 Python 环境验证，并能使用变量、基本类型、print() 和 input() 编写可交互脚本。",
        "references": [
            {
                "title": "Python 官方入门教程",
                "url": "https://docs.python.org/zh-cn/3/tutorial/introduction.html",
                "type": "documentation",
            }
        ],
    }


def _build_python_overview_fallback(
    node_title: str,
    node_desc: str | None,
    objectives: list[str],
) -> dict[str, Any]:
    """Provide substantive offline material for Python overview/history nodes."""
    return {
        "introduction": (
            f"# {node_title}\n\n"
            f"{node_desc or '认识 Python 的定位、运行方式、发展脉络和主要应用方向。'}"
            "本单元不会停留在术语罗列，而是通过可运行代码建立第一印象。"
        ),
        "prerequisites": ["会使用文件管理器和终端的基本操作", "无需编程经验"],
        "objectives": objectives,
        "estimated_minutes": 45,
        "completion_criteria": [
            "能解释 Python 解释器如何执行脚本",
            "能说出动态类型、缩进语法和丰富生态的含义",
            "能根据任务判断 Python 是否适合，并运行第一个脚本",
        ],
        "sections": [
            {
                "section_id": "sec-1",
                "title": "Python 是什么：语言、解释器与程序",
                "order": 1,
                "content": """## Python 不只是一个应用程序

Python 同时指一门编程语言及其常用解释器。你编写的 `.py` 文件是源代码；运行 `python hello.py` 时，解释器读取代码、编译为字节码，再由 Python 虚拟机执行。

```python
language = "Python"
year = 1991
print(f"{language} 在 {year} 年发布首个公开版本")
```

这段程序展示了变量、字符串、数字与函数调用。保存为 `hello.py` 后执行 `python hello.py`，终端应输出一行文字。

### 自检

- `.py` 文件和 Python 解释器分别扮演什么角色？
- 修改 `year` 后，输出为什么会随之改变？""",
                "concepts": ["Python 语言", "解释器", "源代码与字节码", "Python 虚拟机"],
                "examples": [{"title": "运行第一个 Python 脚本", "description": "保存并执行 hello.py"}],
                "code_examples": [{"title": "语言信息输出", "language": "python"}],
                "common_mistakes": [
                    {"mistake": "把代码编辑器当作 Python 解释器", "correction": "编辑器负责写代码，解释器负责执行代码。"}
                ],
                "checkpoints": ["解释源代码到输出之间的执行链路", "成功运行 hello.py"],
                "mind_map_nodes": ["语言与解释器", "源代码", "字节码", "虚拟机执行"],
            },
            {
                "section_id": "sec-2",
                "title": "发展脉络与设计理念",
                "order": 2,
                "content": """## 从可读性出发的语言设计

Guido van Rossum 在 1989 年圣诞节期间开始设计 Python，1991 年发布首个公开版本。Python 2 与 Python 3 曾长期并存；Python 2 已于 2020 年停止官方支持，新项目应使用 Python 3。

Python 强调代码可读性：缩进直接表示代码块，常见操作尽量使用清楚的语法表达。

```python
scores = [72, 91, 85]

for score in scores:
    if score >= 80:
        print(score, "达到目标")
```

冒号后的缩进不是装饰。如果 `if` 下方没有保持一致缩进，解释器会报告 `IndentationError`。

### 版本选择

学习时优先安装仍受支持的 Python 3 版本。阅读教程时如果看到 `print x`、`raw_input()` 等写法，需要警惕它可能是 Python 2 资料。""",
                "concepts": ["Python 3", "可读性", "缩进代码块", "版本兼容"],
                "examples": [{"title": "用缩进表达循环与条件", "description": "筛选达到目标的分数"}],
                "code_examples": [{"title": "成绩筛选", "language": "python"}],
                "common_mistakes": [
                    {"mistake": "混用 Python 2 教程", "correction": "确认资料面向 Python 3，并检查发布日期。"},
                    {"mistake": "随意混用制表符和空格", "correction": "统一使用 4 个空格缩进。"},
                ],
                "checkpoints": ["说明为什么新项目使用 Python 3", "识别一个缩进代码块"],
                "mind_map_nodes": ["1991 首次发布", "Python 3", "可读性优先", "缩进语法"],
            },
            {
                "section_id": "sec-3",
                "title": "核心特征与运行模型",
                "order": 3,
                "content": """## 动态类型与丰富的标准库

Python 变量保存的是对象引用，同一个变量名可以先后指向不同类型的对象。这称为动态类型，但不等于“没有类型”——每个对象仍有明确类型。

```python
value = 42
print(type(value))

value = "forty-two"
print(type(value))
```

Python 自带被称为“标准库”的大量模块。例如 `pathlib` 处理路径，`json` 处理 JSON，`statistics` 完成常见统计计算。

```python
from statistics import mean

temperatures = [23.5, 25.0, 24.2]
print(mean(temperatures))
```

第三方包通常通过 `pip` 安装，项目中建议使用虚拟环境隔离依赖。""",
                "concepts": ["动态类型", "对象与引用", "标准库", "第三方包", "虚拟环境"],
                "examples": [{"title": "观察变量类型变化", "description": "使用 type() 检查对象类型"}],
                "code_examples": [{"title": "平均温度", "language": "python"}],
                "common_mistakes": [
                    {"mistake": "认为动态类型表示对象没有类型", "correction": "类型属于对象，变量名只是引用对象。"}
                ],
                "checkpoints": ["解释变量名与对象的关系", "使用一个标准库模块"],
                "mind_map_nodes": ["动态类型", "对象引用", "标准库", "pip 生态", "虚拟环境"],
            },
            {
                "section_id": "sec-4",
                "title": "应用版图与技术选择",
                "order": 4,
                "content": """## Python 擅长解决哪些问题

Python 常用于自动化脚本、Web 后端、数据分析、人工智能、科学计算、测试与运维工具。它的优势是开发速度快、库丰富、跨平台；代价是解释执行通常不适合极端性能敏感的底层循环，移动端原生开发也不是其主要场景。

| 场景 | 常见工具 | Python 的价值 |
|---|---|---|
| 自动化 | pathlib、requests | 用少量代码串联文件和服务 |
| Web 后端 | FastAPI、Django | 快速构建 API 和业务系统 |
| 数据与 AI | NumPy、pandas、PyTorch | 成熟的计算与模型生态 |
| 测试 | pytest | 易读、易组合的自动化测试 |

选择语言时不要只问“Python 流不流行”，而要比较任务约束：团队经验、性能目标、部署环境、现有生态和维护成本。

### 小实践

列出一个你想自动化的重复任务，写清输入、处理步骤和期望输出。它将成为后续学习中的第一个 Python 小项目。""",
                "concepts": ["自动化", "Web 后端", "数据分析与 AI", "适用边界", "技术选型"],
                "examples": [{"title": "按约束选择技术", "description": "比较生态、性能和维护成本"}],
                "code_examples": [],
                "common_mistakes": [
                    {"mistake": "不分析约束就认为 Python 适合所有项目", "correction": "同时评估性能、平台、生态和团队能力。"}
                ],
                "checkpoints": ["说出三个 Python 典型场景", "说出一个不应优先选择 Python 的场景"],
                "mind_map_nodes": ["自动化", "Web 开发", "数据与 AI", "测试运维", "适用边界"],
            },
        ],
        "practice_tasks": [
            {
                "task_id": "pt-1",
                "title": "运行并修改第一个脚本",
                "description": "运行 hello.py，修改变量后观察输出变化，并记录解释器版本。",
                "difficulty": "beginner",
            },
            {
                "task_id": "pt-2",
                "title": "绘制执行过程",
                "description": "用四个方框表示源代码、解释器、字节码和执行结果之间的关系。",
                "difficulty": "beginner",
            },
            {
                "task_id": "pt-3",
                "title": "完成技术选型卡",
                "description": "选择一个真实任务，从生态、性能、部署和维护四方面判断是否使用 Python。",
                "difficulty": "beginner",
            },
        ],
        "project": {
            "title": "Python 应用场景调查",
            "description": "选择一个感兴趣的 Python 项目，说明它解决的问题及使用 Python 的理由。",
            "steps": ["选择项目", "确认输入与输出", "分析 Python 优势与限制", "形成一页结论"],
            "deliverables": ["场景分析卡", "技术选择结论", "一个可运行的入门脚本"],
        },
        "summary": "你已经建立了 Python 的整体坐标：它由语言和解释器共同构成，强调可读性，拥有动态类型和丰富生态，并在自动化、Web、数据与 AI 等领域广泛使用。",
        "references": [
            {"title": "Python 官方教程", "url": "https://docs.python.org/zh-cn/3/tutorial/", "type": "documentation"},
            {"title": "Python 官方历史与常见问题", "url": "https://docs.python.org/zh-cn/3/faq/general.html", "type": "documentation"},
        ],
    }


def _build_python_topic_fallback(
    node_title: str,
    node_desc: str | None,
    node_difficulty: str,
    objectives: list[str],
) -> dict[str, Any]:
    """Build distinct, runnable Python material for non-overview path nodes."""
    if any(keyword in node_title for keyword in ("错误", "调试", "异常")):
        topic_key = "debugging"
    elif any(keyword in node_title for keyword in ("性能", "优化", "进阶")):
        topic_key = "performance"
    elif any(keyword in node_title for keyword in ("项目", "实战")):
        topic_key = "project"
    elif any(keyword in node_title for keyword in ("生态", "扩展", "包管理")):
        topic_key = "ecosystem"
    elif any(keyword in node_title for keyword in ("工具", "操作")):
        topic_key = "tooling"
    elif any(keyword in node_title for keyword in ("模式", "最佳实践", "规范")):
        topic_key = "practices"
    elif any(keyword in node_title for keyword in ("总结", "持续学习", "复习")):
        topic_key = "review"
    elif "算法" in node_title:
        topic_key = "algorithms"
    else:
        topic_key = "core"

    profiles: dict[str, dict[str, Any]] = {
        "core": {
            "label": "Python 核心语言机制",
            "concepts": ["对象与变量", "可变与不可变类型", "控制流", "函数与作用域", "模块"],
            "notes": [
                "变量名引用对象，赋值不会自动复制对象",
                "list、dict、set 可变；int、str、tuple 通常不可变",
                "函数通过参数、返回值和异常组成清晰接口",
                "模块把相关定义放入独立文件并通过 import 复用",
            ],
            "mechanism": "Python 执行赋值时先计算右侧对象，再让左侧名称指向它。函数调用会创建局部作用域；名称查找遵循局部、闭包、全局、内置的顺序。",
            "code": """def summarize(scores: list[int]) -> tuple[int, float]:
    passed = [score for score in scores if score >= 60]
    average = sum(scores) / len(scores)
    return len(passed), average

count, average = summarize([58, 76, 91])
print(count, round(average, 1))""",
            "mistake": "用可变对象作为函数默认参数",
            "correction": "默认值使用 None，在函数内部创建新列表或字典。",
            "practice": "编写一个接收成绩列表并返回及格人数、最高分和平均分的函数。",
        },
        "tooling": {
            "label": "Python 开发工具链",
            "concepts": ["解释器", "虚拟环境", "pip", "代码编辑器", "pytest"],
            "notes": [
                "python --version 确认当前解释器版本",
                "python -m venv .venv 为项目隔离依赖",
                "python -m pip install 包名确保 pip 属于当前解释器",
                "pytest 自动发现 test_ 开头的测试函数",
            ],
            "mechanism": "虚拟环境通过独立的解释器入口和 site-packages 目录隔离依赖。激活环境只是调整终端 PATH；使用 python -m pip 能进一步避免装错环境。",
            "code": """import sys
from pathlib import Path

print("解释器:", sys.executable)
print("Python:", sys.version.split()[0])
print("项目目录:", Path.cwd())""",
            "mistake": "终端显示安装成功，但运行时仍提示找不到包",
            "correction": "检查 sys.executable，并使用同一解释器执行 python -m pip install。",
            "practice": "创建 .venv，安装 pytest，运行一个包含两条断言的测试文件。",
        },
        "practices": {
            "label": "可维护的 Python 代码",
            "concepts": ["PEP 8", "单一职责", "类型标注", "数据类", "自动化测试"],
            "notes": [
                "函数只承担一个清晰职责并使用动词命名",
                "类型标注表达接口契约，但不会自动完成运行时校验",
                "dataclass 适合承载结构明确的数据",
                "测试同时覆盖正常路径、边界值和错误输入",
            ],
            "mechanism": "可维护性来自稳定接口和快速反馈。先把输入输出写清，再将副作用限制在边界层，使核心逻辑能够独立测试。",
            "code": """from dataclasses import dataclass

@dataclass(frozen=True)
class Product:
    name: str
    price: float

def total(products: list[Product]) -> float:
    return round(sum(item.price for item in products), 2)

print(total([Product("book", 39.9), Product("pen", 3.5)]))""",
            "mistake": "把文件读取、数据计算和输出格式化全部写在一个长函数中",
            "correction": "拆分 I/O、业务逻辑和展示层，并为纯函数编写测试。",
            "practice": "重构一个长脚本：提取数据模型、计算函数和 main() 入口。",
        },
        "performance": {
            "label": "Python 性能分析与优化",
            "concepts": ["时间复杂度", "性能测量", "生成器", "缓存", "向量化"],
            "notes": [
                "先用 timeit 或 cProfile 找到热点，再决定是否优化",
                "用 set 做成员检查通常比 list 更适合大量查询",
                "生成器按需产生元素，可降低峰值内存",
                "数据计算可考虑 NumPy 向量化或把热点下沉到扩展库",
            ],
            "mechanism": "优化目标必须可测量。算法复杂度通常比语句级微调更重要；I/O 密集和 CPU 密集任务需要不同的并发策略。",
            "code": """from timeit import timeit

values = list(range(10_000))
lookup = set(values)

list_time = timeit(lambda: 9_999 in values, number=1_000)
set_time = timeit(lambda: 9_999 in lookup, number=1_000)
print(round(list_time, 4), round(set_time, 4))""",
            "mistake": "凭感觉改写代码，却没有基准测试",
            "correction": "固定输入和运行次数，记录优化前后时间与内存，再比较正确性。",
            "practice": "比较 list 与 set 的成员查询，并解释数据规模变化时的差异。",
        },
        "debugging": {
            "label": "异常处理与调试",
            "concepts": ["Traceback", "异常类型", "try/except", "logging", "断点调试"],
            "notes": [
                "Traceback 应从最后一行的异常类型和消息开始阅读",
                "只捕获能够处理的具体异常，避免裸 except",
                "日志保留时间、级别和上下文，便于复现线上问题",
                "断点可以检查变量、调用栈和分支执行路径",
            ],
            "mechanism": "异常会沿调用栈向上传播，直到遇到匹配的 except；若无人处理，解释器输出完整 Traceback 并终止当前程序。",
            "code": """import logging

logging.basicConfig(level=logging.INFO)

def parse_age(raw: str) -> int:
    try:
        age = int(raw)
    except ValueError as exc:
        raise ValueError("年龄必须是整数") from exc
    if age < 0:
        raise ValueError("年龄不能为负数")
    return age

logging.info("age=%s", parse_age("18"))""",
            "mistake": "使用 except Exception: pass 吞掉所有错误",
            "correction": "捕获具体异常，记录上下文，并在无法恢复时继续抛出。",
            "practice": "为字符串转整数函数补充错误消息、日志和三个边界测试。",
        },
        "project": {
            "label": "Python 项目工程化",
            "concepts": ["需求拆分", "包结构", "配置", "命令行接口", "测试与交付"],
            "notes": [
                "先定义用户场景、输入输出和验收标准",
                "src 与 tests 分离，业务逻辑避免依赖交互式输入",
                "配置与密钥不硬编码进源码",
                "README 写清安装、运行、测试和示例",
            ],
            "mechanism": "项目从入口层接收参数，交给可测试的业务函数处理，再由边界层负责文件或网络 I/O。分层让变化被限制在局部。",
            "code": """from pathlib import Path

def count_lines(path: Path) -> int:
    with path.open(encoding="utf-8") as handle:
        return sum(1 for _ in handle)

def main() -> None:
    target = Path("README.md")
    print(f"{target}: {count_lines(target)} lines")

if __name__ == "__main__":
    main()""",
            "mistake": "一开始就堆功能，没有验收标准和可运行最小版本",
            "correction": "先交付一个端到端最小闭环，再按测试保护逐步扩展。",
            "practice": "实现文件统计 CLI，包含 README、参数校验和至少三个测试。",
        },
        "ecosystem": {
            "label": "Python 标准库与第三方生态",
            "concepts": ["标准库", "PyPI", "语义化版本", "依赖锁定", "许可证"],
            "notes": [
                "优先检查 pathlib、json、csv、sqlite3 等标准库是否满足需求",
                "从 PyPI 安装前检查维护状态、发布频率、文档和许可证",
                "应用项目应记录可复现的依赖版本",
                "升级依赖前阅读变更日志并运行完整测试",
            ],
            "mechanism": "import 根据模块搜索路径加载代码；包管理器负责下载发行物和解析依赖，但兼容性与供应链风险仍需项目自行验证。",
            "code": """import importlib.metadata
from importlib.util import find_spec

package = "pytest"
if find_spec(package):
    print(package, importlib.metadata.version(package))
else:
    print(package, "not installed")""",
            "mistake": "看到包名相似就直接安装并在生产中使用",
            "correction": "核对官方项目链接、维护状态、许可证和安全记录。",
            "practice": "为一个需求比较标准库方案与第三方包方案，记录选择依据。",
        },
        "review": {
            "label": "Python 知识整合与持续学习",
            "concepts": ["知识地图", "刻意练习", "项目复盘", "文档检索", "反馈循环"],
            "notes": [
                "用语言基础、工具链、工程实践和应用方向组织知识地图",
                "练习应包含输出目标、即时反馈和逐步增加的难度",
                "项目复盘记录决策、错误、验证方法和可改进点",
                "遇到问题优先构造最小复现，再查官方文档",
            ],
            "mechanism": "持续学习依赖短反馈循环：提出假设、编写最小实验、观察结果、解释差异并更新知识模型。",
            "code": """topics = {
    "syntax": 3,
    "testing": 2,
    "debugging": 1,
}

next_topic = min(topics, key=topics.get)
print("下一步优先练习:", next_topic)""",
            "mistake": "只收藏教程，不输出代码、测试或复盘记录",
            "correction": "每个学习主题至少形成一个可运行实验和一条复盘结论。",
            "practice": "制定两周计划：每天一个最小实验，每三天完成一次复盘。",
        },
        "algorithms": {
            "label": "Python 算法与数据结构",
            "concepts": ["复杂度", "列表与字典", "栈与队列", "排序与搜索", "边界条件"],
            "notes": [
                "选择结构时同时考虑访问、插入、删除和成员检查成本",
                "dict 与 set 基于哈希，平均成员检查接近常数时间",
                "二分搜索要求输入有序，并始终维护搜索区间不变量",
                "正确性证明和边界测试应先于微观性能优化",
            ],
            "mechanism": "算法通过不变量保证每一步仍朝正确答案收敛，通过时间与空间复杂度描述输入规模增长时的资源变化。",
            "code": """def binary_search(values: list[int], target: int) -> int:
    left, right = 0, len(values) - 1
    while left <= right:
        middle = (left + right) // 2
        if values[middle] == target:
            return middle
        if values[middle] < target:
            left = middle + 1
        else:
            right = middle - 1
    return -1

print(binary_search([2, 4, 7, 9, 12], 9))""",
            "mistake": "在无序列表上直接使用二分搜索",
            "correction": "先确认有序性，或选择适合无序数据的查找结构。",
            "practice": "为二分搜索补充空列表、首尾元素、不存在目标四类测试。",
        },
    }
    profile = profiles[topic_key]
    concept_lines = "\n".join(f"- **{concept}**" for concept in profile["concepts"])
    note_lines = "\n".join(f"- {note}" for note in profile["notes"])
    code = profile["code"]
    label = profile["label"]
    prerequisite = "已完成 Python 环境配置与基本语法" if topic_key != "core" else "能够运行 Python 脚本"

    sections = [
        {
            "section_id": "sec-1",
            "title": f"{label}知识地图",
            "order": 1,
            "content": f"## 本节点解决什么问题\n\n{node_desc or label}\n\n### 核心概念\n\n{concept_lines}\n\n### 学习路线\n\n{note_lines}",
            "concepts": profile["concepts"],
            "examples": [],
            "code_examples": [],
            "common_mistakes": [],
            "checkpoints": [f"能否说出{label}中的三个核心概念？"],
            "mind_map_nodes": profile["concepts"],
        },
        {
            "section_id": "sec-2",
            "title": "机制与决策依据",
            "order": 2,
            "content": f"## 核心机制\n\n{profile['mechanism']}\n\n### 决策检查\n\n{note_lines}",
            "concepts": profile["concepts"][:4],
            "examples": [{"title": "按约束做技术决策", "description": profile["notes"][0]}],
            "code_examples": [],
            "common_mistakes": [],
            "checkpoints": ["能否解释机制，而不是只记住结论？"],
            "mind_map_nodes": ["核心机制", "输入约束", "决策依据", "结果验证"],
        },
        {
            "section_id": "sec-3",
            "title": "可运行示例与逐步验证",
            "order": 3,
            "content": f"## 先运行，再修改\n\n```python\n{code}\n```\n\n先预测输出，再运行验证；随后修改一个输入或边界条件，解释结果为什么变化。",
            "concepts": ["最小可运行示例", "预测输出", "修改输入", "验证结果"],
            "examples": [{"title": f"{label}最小实验", "description": "运行、修改并解释示例"}],
            "code_examples": [{"title": f"{label}示例", "language": "python", "code": code}],
            "common_mistakes": [],
            "checkpoints": ["代码能否直接运行？", "能否解释每个关键步骤？"],
            "mind_map_nodes": ["运行示例", "预测输出", "修改边界", "解释差异"],
        },
        {
            "section_id": "sec-4",
            "title": "工程实践、易错点与验收",
            "order": 4,
            "content": (
                f"## 常见误区\n\n**错误做法：** {profile['mistake']}\n\n"
                f"**改进方式：** {profile['correction']}\n\n"
                f"## 实践任务\n\n{profile['practice']}\n\n"
                "### 验收标准\n\n- 结果可以重复运行\n- 至少覆盖一个边界条件\n- 能解释关键决策\n- 保留代码与简短复盘"
            ),
            "concepts": ["错误识别", "边界测试", "可重复运行", "复盘"],
            "examples": [{"title": "从错误到修复", "description": profile["correction"]}],
            "code_examples": [],
            "common_mistakes": [{"mistake": profile["mistake"], "correction": profile["correction"]}],
            "checkpoints": ["是否覆盖边界条件？", "是否保留可重复的验证步骤？"],
            "mind_map_nodes": ["常见误区", "改进方式", "实践任务", "验收标准"],
        },
    ]

    return {
        "introduction": f"# {node_title}\n\n{node_desc or label}。本单元使用具体机制、可运行示例和验收标准组织学习。",
        "prerequisites": [prerequisite],
        "objectives": objectives,
        "estimated_minutes": 55 if node_difficulty == "advanced" else 45,
        "completion_criteria": [*objectives, "完成一个可运行实验并解释关键决策"],
        "sections": sections,
        "practice_tasks": [
            {"task_id": "pt-1", "title": "复现示例", "description": "运行示例并记录输出。", "difficulty": node_difficulty},
            {"task_id": "pt-2", "title": "边界改造", "description": "修改一个输入或边界条件并解释差异。", "difficulty": node_difficulty},
            {"task_id": "pt-3", "title": "主题实践", "description": profile["practice"], "difficulty": node_difficulty},
        ],
        "project": {
            "title": f"{label}实践",
            "description": profile["practice"],
            "steps": ["明确输入输出", "完成最小实现", "覆盖边界条件", "运行测试", "记录复盘"],
            "deliverables": ["可运行代码", "验证结果", "关键决策说明"],
        },
        "summary": f"你已经完成{label}的概念梳理、机制分析、代码验证和工程实践。",
        "references": [
            {"title": "Python 官方教程", "url": "https://docs.python.org/zh-cn/3/tutorial/", "type": "documentation"},
            {"title": "Python 标准库", "url": "https://docs.python.org/zh-cn/3/library/", "type": "documentation"},
        ],
    }


@register_handler("knowledge_index")
async def _execute_knowledge_index(db: Any, task: Any) -> dict[str, Any]:
    """Execute a knowledge indexing task.

    Pipeline:
      1. Download file from object storage
      2. Parse document (PDF/TXT/MD/DOCX/CSV/JSON)
      3. Chunk into 800-1200 token segments
      4. Insert chunks with new index_version
      5. Activate new version (deletes old chunks)
      6. Set document status to 'ready'
    """
    from sqlalchemy import select

    from app.models.knowledge import KnowledgeDocument
    from app.services.chunker import chunk_sections, chunks_to_dicts
    from app.services.document_parser import parse_document
    from app.services.knowledge import KnowledgeService
    from app.services.storage import get_object_storage

    doc_id = task.target_id
    if not doc_id:
        raise ValueError("Document ID is required for knowledge_index task")

    # Step 1: Get document
    result = await db.execute(select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise ValueError(f"Document {doc_id} not found")

    # Determine if this is a reindex (doc already has a version)
    is_reindex = doc.active_index_version is not None
    new_version = (doc.active_index_version or 0) + 1

    storage = get_object_storage()
    service = KnowledgeService(db, storage=storage)

    try:
        # Step 2: Download from object storage
        await update_task_status(db, task.id, "running", progress=10, stage="downloading", message="下载文件...")
        content_bytes = await storage.get(doc.storage_key)

        # Step 3: Parse document
        await update_task_status(db, task.id, "running", progress=30, stage="parsing", message="解析文档...")
        sections = parse_document(content_bytes, doc.mime_type, doc.filename)

        if not sections:
            raise ValueError("Document produced no parseable content")

        # Step 4: Chunk
        await update_task_status(db, task.id, "running", progress=50, stage="chunking", message="分块处理...")
        chunks = chunk_sections(sections)
        chunk_dicts = chunks_to_dicts(chunks)

        if not chunk_dicts:
            raise ValueError("Chunking produced no chunks")

        # Step 5: Insert new chunks
        await update_task_status(db, task.id, "running", progress=70, stage="indexing", message="写入索引...")
        await service.add_chunks(doc_id, chunk_dicts, index_version=new_version)

        # Step 6: Activate new version (deletes old chunks atomically)
        await service.activate_version(doc_id, new_version)

        # Step 7: Mark as ready
        doc.status = "ready"
        doc.operation_status = "ready"
        doc.error = None
        await db.flush()

        return {
            "document_id": doc_id,
            "chunks": len(chunk_dicts),
            "index_version": new_version,
            "reindex": is_reindex,
        }

    except Exception as e:
        # Mark document as failed
        try:
            doc.status = "failed"
            doc.operation_status = "failed"
            doc.error = str(e)
            await db.flush()
        except Exception:
            logger.debug("doc_status_update_failed", exc_info=True)
        raise


@register_handler("knowledge_reindex")
async def _execute_knowledge_reindex(db: Any, task: Any) -> dict[str, Any]:
    """Execute a knowledge reindex — reuses the index logic.

    The reindex handler is separate so we can set the document to
    'reindexing' status before the task runs (done in the API).
    The handler itself uses the same pipeline as knowledge_index,
    but the document already has active_index_version set, so
    a new version number is generated automatically.
    """
    return await _execute_knowledge_index(db, task)


@register_handler("learning_lecture_generation")
async def _execute_lecture_generation(db: Any, task: Any) -> dict[str, Any]:
    """Generate an expanded lecture for an existing unit content."""
    import json

    from sqlalchemy import select

    from app.models.goal import LearningGoal
    from app.models.path import LearningNode, LearningPath
    from app.models.unit import LearningUnitContent, LearningUnitContentVersion
    from app.services.llm import LLMError, llm_json

    node_id = task.target_id
    user_id = task.user_id
    metadata = task.target_metadata or {}
    path_id = metadata.get("path_id", "")

    # Step 1: Analyze existing content
    await update_task_status(db, task.id, "running", progress=10, stage="analyzing", message="正在分析现有单元内容...")

    content_result = await db.execute(
        select(LearningUnitContent).where(
            LearningUnitContent.node_id == node_id,
            LearningUnitContent.user_id == user_id,
        )
    )
    unit_content = content_result.scalar_one_or_none()

    existing = unit_content.content if unit_content else None
    if unit_content and unit_content.active_version_id:
        version_result = await db.execute(
            select(LearningUnitContentVersion).where(
                LearningUnitContentVersion.id == unit_content.active_version_id
            )
        )
        active_version = version_result.scalar_one_or_none()
        if active_version and active_version.content:
            existing = active_version.content

    if not existing:
        raise ValueError("单元内容尚未生成，无法生成讲义")

    if isinstance(existing, str):
        existing = json.loads(existing)

    # Step 2: Load node context
    node_result = await db.execute(select(LearningNode).where(LearningNode.id == node_id))
    node = node_result.scalar_one_or_none()
    node_title = node.title if node else "未知节点"
    node_difficulty = node.difficulty if node else "beginner"
    objectives = existing.get("objectives", [f"理解{node_title}的核心概念"])

    # Look up goal context
    goal_title = ""
    if path_id:
        path_result = await db.execute(select(LearningPath).where(LearningPath.id == path_id))
        path = path_result.scalar_one_or_none()
        if path and path.goal_id:
            goal_result = await db.execute(select(LearningGoal).where(LearningGoal.id == path.goal_id))
            goal = goal_result.scalar_one_or_none()
            if goal:
                goal_title = goal.title or ""

    # Step 3: Provide the canonical structured material to the lecture LLM.
    # Keep section metadata so source_section_id and mind-map concepts survive.
    source_payload = {
        "introduction": existing.get("introduction"),
        "prerequisites": existing.get("prerequisites", []),
        "objectives": existing.get("objectives", []),
        "completion_criteria": existing.get("completion_criteria", []),
        "sections": existing.get("sections", []),
        "practice_tasks": existing.get("practice_tasks", []),
        "project": existing.get("project"),
        "summary": existing.get("summary"),
    }
    existing_summary = json.dumps(source_payload, ensure_ascii=False)[:24000]
    record_agent_step(
        task,
        agent_key="source_material_analyzer",
        label="原始材料分析器",
        status="completed",
        summary=f"已整理 {len(source_payload['sections'])} 个课程章节及其学习目标。",
        artifact_type="讲义生成上下文",
    )

    # Step 4: LLM generation
    lecture_data = None
    lecture_source = "llm"
    try:
        record_agent_step(
            task,
            agent_key="lecture_generator",
            label="专业讲义生成智能体",
            status="running",
            summary="正在深化概念讲解、案例、代码和常见误区。",
            artifact_type="专业课程讲义",
        )
        await update_task_status(
            db, task.id, "running", progress=25, stage="generating", message="智能体正在生成详细讲义..."
        )

        from app.prompts.agents import LECTURE_GENERATOR_SYSTEM, lecture_generator_user

        user_msg = lecture_generator_user(node_title, node_difficulty, objectives, existing_summary, goal_title)
        lecture_data = await llm_json(LECTURE_GENERATOR_SYSTEM, user_msg, temperature=0.6, max_tokens=12000)

        if not lecture_data.get("sections") or len(lecture_data["sections"]) < 2:
            raise LLMError("Insufficient lecture sections generated")

        await update_task_status(
            db, task.id, "running", progress=80, stage="finalizing", message="讲义内容生成完成，正在整理..."
        )

    except (LLMError, KeyError, ValueError) as e:
        logger.warning("llm_lecture_fallback", error=str(e))
        await update_task_status(
            db, task.id, "running", progress=30, stage="generating", message="LLM 不可用，使用模板生成讲义..."
        )

    # Step 5: Fallback
    if lecture_data is None:
        lecture_data = _build_fallback_lecture(node_title, node_difficulty, existing)
        lecture_source = "fallback"

    lecture_data, lecture_quality = _normalize_lecture_material(lecture_data, existing)
    if lecture_quality["score"] < 60 and lecture_source == "llm":
        logger.warning(
            "llm_lecture_quality_fallback",
            node_id=node_id,
            score=lecture_quality["score"],
            issues=lecture_quality["issues"],
        )
        lecture_data, lecture_quality = _normalize_lecture_material(
            _build_fallback_lecture(node_title, node_difficulty, existing),
            existing,
        )
        lecture_source = "fallback_quality_gate"
    lecture_data["generation_metadata"] = {
        "source": lecture_source,
        "quality_report": lecture_quality,
        "source_content_version_id": unit_content.active_version_id if unit_content else None,
    }
    record_agent_step(
        task,
        agent_key="lecture_generator",
        label="专业讲义生成智能体",
        status="completed",
        summary=f"讲义生成完成，来源为 {lecture_source}，质量分 {lecture_quality['score']}。",
        artifact_type="专业课程讲义",
    )
    record_agent_step(
        task,
        agent_key="lecture_quality_gate",
        label="讲义质量校验器",
        status="completed",
        summary="已检查章节映射、正文深度、代码块和通用占位描述。",
        artifact_type="讲义质量报告",
    )

    # Step 6: Save to independent LearningLecture
    await update_task_status(db, task.id, "running", progress=90, stage="saving", message="正在保存讲义内容...")

    from app.models.unit import LearningLecture

    lecture_result = await db.execute(
        select(LearningLecture).where(
            LearningLecture.node_id == node_id,
            LearningLecture.user_id == user_id,
        )
    )
    lecture = lecture_result.scalar_one_or_none()

    if lecture:
        lecture.content = lecture_data
        lecture.status = "ready"
        lecture.active_task_id = None
    else:
        lecture = LearningLecture(
            id=__import__("uuid").uuid4().hex[:26],
            user_id=user_id,
            path_id=path_id,
            node_id=node_id,
            status="ready",
            content=lecture_data,
        )
        db.add(lecture)

    await db.flush()

    await update_task_status(db, task.id, "running", progress=100, stage="completed", message="讲义生成完成")

    return {"lecture_id": lecture.id, "node_id": node_id}


def _normalize_lecture_material(
    lecture: dict[str, Any],
    source: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Normalize lecture sections and preserve links to canonical source sections."""
    normalized = dict(lecture)
    source_sections_raw = source.get("sections")
    source_sections: list[Any] = source_sections_raw if isinstance(source_sections_raw, list) else []
    raw_lecture_sections = lecture.get("sections")
    lecture_sections: list[Any] = raw_lecture_sections if isinstance(raw_lecture_sections, list) else []
    sections: list[dict[str, Any]] = []
    for index, raw in enumerate(lecture_sections):
        if not isinstance(raw, dict):
            continue
        source_section = source_sections[index] if index < len(source_sections) else {}
        section = dict(raw)
        section.update(
            {
                "section_id": str(raw.get("section_id") or f"lec-{index + 1}"),
                "source_section_id": str(
                    raw.get("source_section_id")
                    or (source_section.get("section_id") if isinstance(source_section, dict) else "")
                    or f"sec-{index + 1}"
                ),
                "title": str(raw.get("title") or source_section.get("title") or f"章节 {index + 1}"),
                "content": str(raw.get("content") or source_section.get("content") or ""),
                "order": index + 1,
            }
        )
        sections.append(section)
    normalized["sections"] = sections
    normalized["introduction"] = str(lecture.get("introduction") or source.get("introduction") or "")
    normalized["key_takeaways"] = (
        _string_list(lecture.get("key_takeaways")) or _string_list(source.get("objectives"))
    )
    mistakes = lecture.get("common_mistakes")
    normalized["common_mistakes"] = mistakes if isinstance(mistakes, list) else []
    normalized["summary"] = str(lecture.get("summary") or source.get("summary") or "")

    combined = "\n".join(section["content"] for section in sections)
    code_blocks = combined.count("```") // 2
    generic_phrases = ("内部机制和数据流动方式", "处理完成", "有广泛的应用场景")
    generic_hits = sum(combined.count(phrase) for phrase in generic_phrases)
    score = min(30, len(sections) * 7)
    score += min(40, len(combined) // 100)
    score += min(15, code_blocks * 5)
    score += min(15, len(normalized["common_mistakes"]) * 5)
    score = max(0, min(100, score - generic_hits * 15))
    issues: list[str] = []
    if len(sections) < 4:
        issues.append("讲义章节少于 4 个")
    if len(combined) < 1800:
        issues.append("讲义正文深度不足")
    if generic_hits:
        issues.append("讲义包含通用占位描述")
    return normalized, {
        "score": score,
        "passed": score >= 70,
        "issues": issues,
        "section_count": len(sections),
        "character_count": len(combined),
        "code_example_count": code_blocks,
    }


def _build_fallback_lecture(node_title: str, node_difficulty: str, existing: dict) -> dict:
    """Use the reviewed unit source directly when lecture generation is unavailable."""
    existing_sections = existing.get("sections", [])

    sections: list[dict[str, Any]] = []
    for i, sec in enumerate(existing_sections):
        title = sec.get("title", f"章节 {i + 1}")
        sections.append(
            {
                "section_id": f"lec-{i + 1}",
                "source_section_id": sec.get("section_id", f"sec-{i + 1}"),
                "title": title,
                "content": sec.get("content", ""),
                "order": i + 1,
            }
        )

    # If no existing sections, create a basic one
    if not sections:
        sections = [
            {
                "section_id": "lec-1",
                "source_section_id": "sec-1",
                "title": node_title,
                "content": existing.get("introduction") or f"请根据学习目标完成「{node_title}」的学习与练习。",
                "order": 1,
            }
        ]

    return {
        "introduction": existing.get("introduction") or f"# {node_title}",
        "sections": sections,
        "key_takeaways": existing.get("objectives", []),
        "common_mistakes": [],
        "summary": existing.get("summary") or f"完成练习后，检查是否达成「{node_title}」的学习目标。",
    }


@celery_app.task(name="tasks.recover_stale")  # type: ignore[untyped-decorator]
def recover_stale_tasks_task() -> dict[str, Any]:
    """Periodic task to recover stale tasks."""
    logger.info("recovering_stale_tasks")

    async def _recover() -> dict[str, Any]:
        factory = get_session_factory()
        async with factory() as db:
            recovered = await recover_stale_tasks(db)
            await _cleanup_engine()
            return {"recovered": len(recovered)}

    return run_async(_recover())  # type: ignore[no-any-return]


@celery_app.task(name="tasks.publish_outbox")  # type: ignore[untyped-decorator]
def publish_outbox_task() -> dict[str, Any]:
    """Periodic task to publish pending outbox events."""
    from app.workers.outbox_publisher import publish_pending_outbox

    async def _publish() -> dict[str, Any]:
        published = await publish_pending_outbox()
        await _cleanup_engine()
        return {"published": published}

    return run_async(_publish())  # type: ignore[no-any-return]
