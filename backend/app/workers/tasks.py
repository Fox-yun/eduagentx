"""Celery worker tasks."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from app.core.database import get_session_factory
from app.workers.celery_app import celery_app
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
                task_result: dict[str, Any] = {}
                if task.task_type == "learning_path_generation":
                    task_result = await _execute_path_generation(db, task)
                elif task.task_type == "learning_unit_generation":
                    task_result = await _execute_unit_generation(db, task)
                elif task.task_type == "knowledge_index":
                    task_result = await _execute_knowledge_index(db, task)
                else:
                    task_result = {"error": f"Unknown task type: {task.task_type}"}

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
                return {"status": "error", "message": str(e)}

    return run_async(_execute())  # type: ignore[no-any-return]


async def _execute_path_generation(db: Any, task: Any) -> dict[str, Any]:
    """Execute a path generation task."""
    import uuid

    from app.services.goal import GoalService
    from app.services.path import PathService

    goal_id = task.target_id
    user_id = task.user_id

    # Update progress
    await update_task_status(db, task.id, "running", progress=20, stage="analyzing", message="分析学习目标...")

    goal_service = GoalService(db)
    goal = await goal_service.get_goal(goal_id, user_id)

    await update_task_status(db, task.id, "running", progress=50, stage="generating", message="生成学习路径...")

    # Generate a simple path
    path_service = PathService(db)

    # Create path
    from app.models.path import LearningPath

    path = LearningPath(
        id=str(uuid.uuid4()),
        user_id=user_id,
        goal_id=goal_id,
        status="draft",
    )
    db.add(path)
    await db.flush()

    # Create version with stages and nodes
    stages = [
        {"title": "基础阶段", "description": "掌握核心概念", "stage_order": 1, "outcome": "理解基础"},
        {"title": "进阶阶段", "description": "深入学习", "stage_order": 2, "outcome": "掌握进阶"},
    ]

    nodes = [
        {
            "title": "核心概念入门",
            "description": "学习基础概念",
            "node_order": 1,
            "level": 1,
            "difficulty": "beginner",
            "estimated_minutes": 30,
            "stage_id": "stage-1",
            "learning_outcomes": ["理解核心概念"],
        },
        {
            "title": "进阶应用",
            "description": "应用所学知识",
            "node_order": 2,
            "level": 2,
            "difficulty": "intermediate",
            "estimated_minutes": 45,
            "stage_id": "stage-2",
            "learning_outcomes": ["能够应用知识"],
        },
    ]

    edges = [
        {"source_node_id": "node-1", "target_node_id": "node-2"},
    ]

    await update_task_status(db, task.id, "running", progress=80, stage="validating", message="校验路径结构...")

    version = await path_service.create_path_version(
        path_id=path.id,
        user_id=user_id,
        stages=stages,
        nodes=nodes,
        edges=edges,
        summary=f"学习路径: {goal.title}",
    )

    # Update goal
    goal.current_path_id = path.id
    await db.flush()

    return {"path_id": path.id, "version": version.version_number}


async def _execute_unit_generation(db: Any, task: Any) -> dict[str, Any]:
    """Execute a unit content generation task."""
    import uuid

    from app.models.unit import LearningUnitContent

    node_id = task.target_id
    user_id = task.user_id

    await update_task_status(db, task.id, "running", progress=30, stage="generating", message="生成单元内容...")

    # Create unit content
    content = LearningUnitContent(
        id=str(uuid.uuid4()),
        user_id=user_id,
        path_id=task.target_metadata.get("path_id", ""),
        path_version_id="1",
        node_id=node_id,
        status="ready",
        content={
            "introduction": "# 学习内容\n\n本单元将介绍核心概念。",
            "objectives": ["理解基础概念", "掌握核心技能"],
            "sections": [{"section_id": "sec-1", "title": "核心概念", "content": "详细内容...", "order": 1}],
            "practice_tasks": [],
            "summary": "本单元总结",
            "references": [],
        },
    )
    db.add(content)
    await db.flush()

    return {"unit_id": content.id, "node_id": node_id}


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


@celery_app.task(name="tasks.recover_stale")  # type: ignore[untyped-decorator]
def recover_stale_tasks_task() -> dict[str, Any]:
    """Periodic task to recover stale tasks."""
    logger.info("recovering_stale_tasks")

    async def _recover() -> dict[str, Any]:
        factory = get_session_factory()
        async with factory() as db:
            recovered = await recover_stale_tasks(db)
            return {"recovered": len(recovered)}

    return run_async(_recover())  # type: ignore[no-any-return]


@celery_app.task(name="tasks.publish_outbox")  # type: ignore[untyped-decorator]
def publish_outbox_task() -> dict[str, Any]:
    """Periodic task to publish pending outbox events."""
    from app.workers.outbox_publisher import publish_pending_outbox

    async def _publish() -> dict[str, Any]:
        published = await publish_pending_outbox()
        return {"published": published}

    return run_async(_publish())  # type: ignore[no-any-return]
