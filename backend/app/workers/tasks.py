"""Celery worker tasks."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from app.core.database import get_session_factory
from app.workers.celery_app import celery_app
from app.workers.task_handlers import get_handler, register_handler
from app.workers.task_runtime import recover_stale_tasks, update_task_status

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

    user_message = f"""请为以下学习目标规划学习路径：

学习目标：{goal.title}
核心主题：{topic}
{f"目标描述：{goal.raw_description}" if goal.raw_description else ""}
{f"当前水平：{goal.current_level}" if goal.current_level else ""}
{f"目标水平：{goal.target_level}" if goal.target_level else ""}

请生成 5-15 个学习节点，确保：
- 节点标题以核心主题「{topic}」为基础，不要包含用户目标的完整表述
- 标题具体明确（例如："{topic} — 指针与引用"而非"{topic}基础"）
- 每个节点 estimated_minutes 在 20-60 之间
- difficulty 按照节点顺序递增
- edges 反映真实的前置依赖关系"""

    # Try LLM generation, fall back to template if LLM unavailable
    stages = []
    nodes = []
    edges = []
    summary = f"学习路径: {goal.title}"

    await update_task_status(
        db, task.id, "running", progress=30, stage="generating", message="智能体正在调用大语言模型生成路径..."
    )
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
    from app.models.unit import LearningUnitContent, LearningUnitContentVersion
    from app.services.llm import LLMError, llm_json

    node_id = task.target_id
    user_id = task.user_id
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

    # ------------------------------------------------
    # LLM call (no DB transaction)
    # ------------------------------------------------
    content_data = None
    await update_task_status(
        db, task.id, "running", progress=25, stage="generating", message="智能体正在调用大语言模型生成内容..."
    )
    try:
        from app.prompts.agents import CONTENT_GENERATOR_SYSTEM, content_generator_user

        system_prompt = CONTENT_GENERATOR_SYSTEM
        user_msg = content_generator_user(node_title, node_desc, node_difficulty, objectives, goal_title)
        if preferences:
            user_msg += f"\n\n用户个性化偏好（请务必参考）：\n{preferences}"

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

    # Review step
    review_passed = True
    try:
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
        content_data["generation_metadata"] = {
            "reviewed": True,
            "review_score": review_result.get("score", 0),
            "review_issues": review_result.get("issues", []),
            "review_summary": review_result.get("summary", ""),
        }
        if not review_passed:
            logger.warning("content_review_failed", node_id=node_id, issues=review_result.get("issues", []))
    except Exception as e:
        logger.warning("review_step_error", error=str(e))

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
    from app.common.datetime import utc_now
    from sqlalchemy import select

    from app.models.unit import LearningUnitContent, LearningUnitContentVersion

    # Load version FOR UPDATE to prevent concurrent completion
    version_result = await txn_db.execute(
        select(LearningUnitContentVersion)
        .where(LearningUnitContentVersion.id == version_id)
        .with_for_update()
    )
    version: LearningUnitContentVersion | None = version_result.scalar_one_or_none()
    if not version:
        raise ValueError(f"Version {version_id} not found")

    # Check task was not cancelled mid-flight
    from app.common.enums import TERMINAL_TASK_STATUSES, TaskStatus
    from app.models.task import BackgroundTask

    task_result = await txn_db.execute(
        select(BackgroundTask).where(BackgroundTask.id == task_id)
    )
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
        select(LearningUnitContent)
        .where(LearningUnitContent.id == version.unit_content_id)
        .with_for_update()
    )
    uc: LearningUnitContent | None = uc_result.scalar_one_or_none()
    if uc:
        # Mark old active version as superseded
        if uc.active_version_id:
            old_version_result = await txn_db.execute(
                select(LearningUnitContentVersion)
                .where(LearningUnitContentVersion.id == uc.active_version_id)
            )
            old_version = old_version_result.scalar_one_or_none()
            if old_version and old_version.id != version.id:
                old_version.status = "superseded"

        # Atomically switch
        uc.active_version_id = version.id
        version.activated_at = utc_now()
        uc.status = "ready"
        uc.active_task_id = None

    await txn_db.commit()
    return {"unit_id": uc.id if uc else version.unit_content_id}


async def _fail_unit_generation(txn_db: Any, version_id: str) -> None:
    """Mark a version as failed without affecting the active version."""
    from sqlalchemy import select

    from app.models.unit import LearningUnitContent, LearningUnitContentVersion

    try:
        version_result = await txn_db.execute(
            select(LearningUnitContentVersion)
            .where(LearningUnitContentVersion.id == version_id)
            .with_for_update()
        )
        version = version_result.scalar_one_or_none()
        if version and version.status == "generating":
            version.status = "failed"

            # Reset unit content to ready (old version still active)
            uc_result = await txn_db.execute(
                select(LearningUnitContent)
                .where(LearningUnitContent.id == version.unit_content_id)
                .with_for_update()
            )
            uc = uc_result.scalar_one_or_none()
            if uc and uc.active_task_id:
                uc.status = "ready" if uc.active_version_id else "failed"
                uc.active_task_id = None

            await txn_db.commit()
    except Exception:
        logger.exception("failed_to_mark_version_failed", version_id=version_id)
        await txn_db.rollback()


def _build_fallback_content(
    node_title: str,
    node_desc: str | None,
    node_difficulty: str,
    objectives: list[str],
) -> dict[str, Any]:
    """Build template-based fallback content when LLM is unavailable."""
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


@register_handler("knowledge_index")
async def _execute_knowledge_index(db: Any, task: Any) -> dict[str, Any]:
    """Execute a knowledge indexing task."""
    import uuid

    from app.models.knowledge import KnowledgeChunk, KnowledgeDocument

    doc_id = task.target_id

    await update_task_status(db, task.id, "running", progress=30, stage="parsing", message="解析文档...")

    # Get document
    from sqlalchemy import select

    result = await db.execute(select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id))
    doc = result.scalar_one_or_none()

    if not doc:
        raise ValueError(f"Document {doc_id} not found")

    await update_task_status(db, task.id, "running", progress=60, stage="chunking", message="分块处理...")

    # Create sample chunks
    chunk = KnowledgeChunk(
        id=str(uuid.uuid4()),
        document_id=doc_id,
        chunk_index=0,
        content="Sample content chunk",
        token_count=10,
    )
    db.add(chunk)

    doc.status = "ready"
    doc.operation_status = "ready"
    await db.flush()

    return {"document_id": doc_id, "chunks": 1}


@register_handler("knowledge_reindex")
async def _execute_knowledge_reindex(db: Any, task: Any) -> dict[str, Any]:
    """Execute a knowledge reindex — reuses the index logic."""
    return await _execute_knowledge_index(db, task)


@register_handler("learning_lecture_generation")
async def _execute_lecture_generation(db: Any, task: Any) -> dict[str, Any]:
    """Generate an expanded lecture for an existing unit content."""
    import json

    from sqlalchemy import select

    from app.models.goal import LearningGoal
    from app.models.path import LearningNode, LearningPath
    from app.models.unit import LearningUnitContent
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

    if not unit_content or not unit_content.content:
        await update_task_status(db, task.id, "failed", stage="error", message="单元内容尚未生成，无法生成讲义")
        return {"error": "No existing content"}

    existing = unit_content.content
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

    # Step 3: Build existing content summary for the LLM
    summary_parts = []
    intro = existing.get("introduction", "")
    if intro:
        summary_parts.append(f"导学介绍：\n{intro[:500]}")
    for sec in existing.get("sections", []):
        title = sec.get("title", "")
        content = sec.get("content", "")
        summary_parts.append(f"章节「{title}」：\n{content[:300]}...")
    existing_summary = "\n\n".join(summary_parts) if summary_parts else "（无现有内容摘要）"

    # Step 4: LLM generation
    lecture_data = None
    try:
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


def _build_fallback_lecture(node_title: str, node_difficulty: str, existing: dict) -> dict:
    """Build a template-based lecture when LLM is unavailable."""
    difficulty_label = {"beginner": "入门", "intermediate": "进阶", "advanced": "高级"}.get(node_difficulty, "基础")
    existing_sections = existing.get("sections", [])

    sections = []
    for i, sec in enumerate(existing_sections):
        title = sec.get("title", f"章节 {i + 1}")
        sections.append(
            {
                "section_id": f"lec-{i + 1}",
                "title": f"{title} — 深度解析",
                "content": (
                    f"## {title} 深度解析\n\n"
                    f"本章节将从{difficulty_label}角度对「{title}」进行更深入的讲解。\n\n"
                    f"### 核心概念\n\n"
                    f"在深入学习之前，我们首先回顾该知识点的核心概念和基本原理。\n\n"
                    f"### Step-by-Step 步骤拆解\n\n"
                    f"1. **第一步**：理解基本定义和适用场景\n"
                    f"2. **第二步**：掌握核心原理和工作机制\n"
                    f"3. **第三步**：通过实际案例加深理解\n"
                    f"4. **第四步**：动手实践，巩固所学知识\n\n"
                    f"### 代码示例\n\n"
                    f"```python\n# {node_title} - {title} 示例\ndef main():\n"
                    f"    # 核心逻辑实现\n    result = process()\n    return result\n\n"
                    f"def process():\n    return '处理完成'\n\n"
                    f"if __name__ == '__main__':\n    print(main())\n```\n\n"
                    f"### 深度解析\n\n"
                    f"以上代码展示了{title}的核心用法。在实际项目中，需要根据具体需求进行调整。\n\n"
                    f"> 💡 提示：建议结合实际项目来理解这些概念，理论与实践相结合效果更佳。"
                ),
                "order": i + 1,
            }
        )

    # If no existing sections, create a basic one
    if not sections:
        sections = [
            {
                "section_id": "lec-1",
                "title": f"{node_title} 深度讲解",
                "content": (
                    f"## {node_title} 深度讲解\n\n"
                    f"本讲义将从{difficulty_label}角度深入讲解{node_title}的核心知识。\n\n"
                    f"### 核心概念\n\n{node_title}是一个重要的知识点。\n\n"
                    f"### 实践指导\n\n建议结合实际案例进行学习。"
                ),
                "order": 1,
            }
        ]

        intro = (
            f"# {node_title} — 详细讲义\n\n本讲义将对{node_title}进行更深入、更全面的讲解，帮助你彻底掌握这一知识点。"
        )
        return {
            "introduction": intro,
            "sections": sections,
            "key_takeaways": [
                f"深入理解{node_title}的核心概念",
                f"掌握{node_title}的实际应用方法",
                "避免常见的理解和操作误区",
            ],
            "common_mistakes": [
                {
                    "mistake": "只看不练",
                    "explanation": "仅阅读讲义而不动手实践，容易遗忘。建议每学完一个章节就完成对应的代码练习。",
                }
            ],
            "summary": f"本讲义深入讲解了{node_title}的核心知识。建议结合原始单元内容和练习题巩固所学。",
        }

    # Return for case where existing sections were used
    return {
        "introduction": f"# {node_title} — 详细讲义\n\n本讲义将对{node_title}进行更深入、更全面的讲解。",
        "sections": sections,
        "key_takeaways": [
            f"深入理解{node_title}的核心概念",
            f"掌握{node_title}的实际应用方法",
            "避免常见的理解和操作误区",
        ],
        "common_mistakes": [
            {
                "mistake": "只看不练",
                "explanation": "仅阅读讲义而不动手实践，容易遗忘。建议每学完一个章节就完成对应的代码练习。",
            }
        ],
        "summary": f"本讲义深入讲解了{node_title}的核心知识。建议结合原始单元内容和练习题巩固所学。",
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
