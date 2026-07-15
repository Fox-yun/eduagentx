"""Regression tests for draft and active path revision sources."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers.path_revision import execute_path_revision


def _scalar(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _scalars(values):
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


@pytest.mark.asyncio
async def test_revision_worker_accepts_draft_source_before_first_activation():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    task = MagicMock()
    task.id = "task-revision-1"
    task.target_id = "request-1"
    task.user_id = "user-1"
    task.target_metadata = {
        "path_id": "path-1",
        "source_version_id": "draft-version-1",
    }

    revision = MagicMock()
    revision.id = "request-1"
    revision.status = "pending"
    revision.revision_request = "增加实践项目"
    revision.source_version_id = "draft-version-1"

    path = MagicMock()
    path.id = "path-1"
    path.active_version_id = None

    version = MagicMock()
    version.id = "draft-version-1"
    version.status = "draft"
    version.summary = "初始草稿"

    stage = MagicMock()
    stage.id = "stage-db-1"
    stage.title = "基础阶段"
    stage.description = "基础知识"
    stage.stage_order = 1
    stage.outcome = "完成基础学习"

    nodes = []
    for index in range(1, 4):
        node = MagicMock()
        node.id = f"node-db-{index}"
        node.logical_key = f"python.topic.{index}"
        node.title = f"知识点 {index}"
        node.description = f"知识点 {index} 的说明"
        node.node_order = index
        node.level = index
        node.difficulty = "beginner"
        node.estimated_minutes = 30
        node.stage_id = stage.id
        node.learning_outcomes = "[]"
        nodes.append(node)

    edges = []
    for index in range(2):
        edge = MagicMock()
        edge.source_node_id = nodes[index].id
        edge.target_node_id = nodes[index + 1].id
        edges.append(edge)

    db.execute = AsyncMock(
        side_effect=[
            _scalar(revision),
            _scalar(path),
            _scalar(version),
            _scalars([stage]),
            _scalars(nodes),
            _scalars(edges),
            _scalar(revision),
        ]
    )

    new_version = MagicMock()
    new_version.id = "draft-version-2"
    new_version.version_number = 2

    with (
        patch("app.workers.path_revision.update_task_status", new_callable=AsyncMock),
        patch("app.workers.path_revision.llm_json", new_callable=AsyncMock, side_effect=RuntimeError("offline")),
        patch(
            "app.workers.path_revision.PathService.create_path_version",
            new_callable=AsyncMock,
            return_value=new_version,
        ),
    ):
        result = await execute_path_revision(db, task)

    assert result["version_id"] == "draft-version-2"
    assert new_version.parent_version_id == "draft-version-1"
    assert new_version.status == "in_review"
    assert revision.status == "completed"
    assert revision.generated_version_id == "draft-version-2"

