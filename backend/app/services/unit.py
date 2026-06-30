"""Unit content and assessment service."""

from __future__ import annotations

import json
import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.datetime import utc_now
from app.core.errors import ApiError
from app.models.path import LearningEdge, LearningPath
from app.models.progress import LearningProgress, MasterySnapshot
from app.models.unit import (
    Assessment,
    AssessmentAnswer,
    AssessmentAttempt,
    AssessmentQuestion,
    LearningUnitContent,
)

logger = structlog.get_logger()

# Pass threshold
PASS_THRESHOLD = 60.0


class UnitService:
    """Unit content and assessment business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_unit_content(
        self,
        path_id: str,
        node_id: str,
        user_id: str,
    ) -> dict[str, object]:
        """Get unit content for a node."""
        from sqlalchemy.orm import selectinload

        result = await self.db.execute(
            select(LearningUnitContent)
            .options(selectinload(LearningUnitContent.versions))
            .where(
                LearningUnitContent.path_id == path_id,
                LearningUnitContent.node_id == node_id,
                LearningUnitContent.user_id == user_id,
            )
        )
        content = result.scalar_one_or_none()

        if not content:
            # Check if there's an active generation task for this node
            from app.common.enums import TaskStatus
            from app.models.task import BackgroundTask

            task_result = await self.db.execute(
                select(BackgroundTask)
                .where(
                    BackgroundTask.target_type == "node",
                    BackgroundTask.target_id == node_id,
                    BackgroundTask.task_type == "learning_unit_generation",
                    BackgroundTask.status.in_(
                        [
                            TaskStatus.PENDING.value,
                            TaskStatus.RUNNING.value,
                        ]
                    ),
                )
                .order_by(BackgroundTask.created_at.desc())
                .limit(1)
            )
            active_task = task_result.scalar_one_or_none()

            if active_task:
                return {
                    "unit_id": f"unit-{node_id}",
                    "path_id": path_id,
                    "path_version": 1,
                    "node_id": node_id,
                    "content_version": 1,
                    "status": "generating",
                    "active_task_id": active_task.id,
                    "introduction": None,
                    "objectives": [],
                    "sections": [],
                    "practice_tasks": [],
                    "summary": None,
                    "references": [],
                    "error": None,
                    "lecture": None,
                    "active_lecture_task_id": None,
                }

            return {
                "unit_id": f"unit-{node_id}",
                "path_id": path_id,
                "path_version": 1,
                "node_id": node_id,
                "content_version": 1,
                "status": "not_generated",
                "active_task_id": None,
                "introduction": None,
                "objectives": [],
                "sections": [],
                "practice_tasks": [],
                "summary": None,
                "references": [],
                "error": None,
                "lecture": None,
                "active_lecture_task_id": None,
            }

        # Prefer active version content, fall back to legacy column
        content_version = 1
        content_data: dict[str, Any] = {}
        pending_version_id: str | None = None
        if content.active_version_id and content.versions:
            active_version = next(
                (v for v in content.versions if v.id == content.active_version_id),
                None,
            )
            if active_version and active_version.content:
                content_data = active_version.content
                content_version = active_version.version_number
            else:
                content_data = content.content or {}
                content_version = content.version_number or 1
        else:
            content_data = content.content or {}
            content_version = content.version_number or 1

        # Find pending version during regeneration
        if content.status == "regenerating" and content.active_task_id and content.versions:
            pending = next(
                (v for v in content.versions if v.status == "generating"),
                None,
            )
            if pending:
                pending_version_id = pending.id

        # Check for active lecture generation task
        from app.common.enums import TaskStatus
        from app.models.task import BackgroundTask

        lecture_task_result = await self.db.execute(
            select(BackgroundTask)
            .where(
                BackgroundTask.target_type == "node",
                BackgroundTask.target_id == node_id,
                BackgroundTask.task_type == "learning_lecture_generation",
                BackgroundTask.user_id == user_id,
                BackgroundTask.status.in_([TaskStatus.PENDING.value, TaskStatus.RUNNING.value]),
            )
            .order_by(BackgroundTask.created_at.desc())
            .limit(1)
        )
        active_lecture_task = lecture_task_result.scalar_one_or_none()

        # Load lecture from independent model (fallback to legacy unit JSON)
        lecture_data: dict[str, object] | None = content_data.get("lecture")
        try:
            from app.models.unit import LearningLecture as LecModel

            lec_result = await self.db.execute(
                select(LecModel).where(
                    LecModel.node_id == node_id,
                    LecModel.user_id == user_id,
                )
            )
            lec_row = lec_result.scalar_one_or_none()
            if lec_row and lec_row.content:
                lecture_data = lec_row.content
        except Exception:
            pass  # Fallback to legacy content_data.get("lecture")

        return {
            "unit_id": content.id,
            "path_id": content.path_id,
            "path_version": 1,
            "node_id": content.node_id,
            "content_version": content_version,
            "status": content.status,
            "active_task_id": content.active_task_id,
            "active_version_id": content.active_version_id,
            "pending_version_id": pending_version_id,
            "introduction": content_data.get("introduction"),
            "objectives": content_data.get("objectives", []),
            "sections": content_data.get("sections", []),
            "practice_tasks": content_data.get("practice_tasks", []),
            "summary": content_data.get("summary"),
            "references": content_data.get("references", []),
            "error": content_data.get("error"),
            "lecture": lecture_data,
            "active_lecture_task_id": active_lecture_task.id if active_lecture_task else None,
        }

    async def _ensure_unit_content(
        self,
        path_id: str,
        node_id: str,
        user_id: str,
        *,
        for_update: bool = False,
    ) -> LearningUnitContent | None:
        """Get or create a LearningUnitContent row, optionally with row lock."""
        from sqlalchemy.orm import selectinload

        stmt = (
            select(LearningUnitContent)
            .options(selectinload(LearningUnitContent.versions))
            .where(
                LearningUnitContent.path_id == path_id,
                LearningUnitContent.node_id == node_id,
                LearningUnitContent.user_id == user_id,
            )
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def generate_content(
        self,
        path_id: str,
        node_id: str,
        user_id: str,
        path_version_id: str | None = None,
    ) -> dict[str, object]:
        """Start generating unit content. Idempotent if already ready or generating."""
        from app.common.enums import TaskStatus
        from app.models.task import BackgroundTask
        from app.models.unit import LearningUnitContentVersion
        from app.models.path import LearningPath

        # Lock the unit content row
        existing = await self._ensure_unit_content(path_id, node_id, user_id, for_update=True)

        # If already ready with content, return existing (idempotent)
        if existing and existing.status == "ready" and existing.active_version_id:
            return {
                "next_step": "ready",
                "unit_content_id": existing.id,
                "active_version_id": existing.active_version_id,
                "active_task_id": None,
            }

        # Check for existing pending/running task
        if existing and existing.active_task_id:
            task_result = await self.db.execute(
                select(BackgroundTask).where(
                    BackgroundTask.id == existing.active_task_id,
                    BackgroundTask.status.in_([TaskStatus.PENDING.value, TaskStatus.RUNNING.value]),
                )
            )
            active_task = task_result.scalar_one_or_none()
            if active_task:
                return {
                    "next_step": "generating",
                    "active_task_id": active_task.id,
                    "unit_content_id": existing.id,
                    "version_id": None,
                }

        # Resolve path_version_id if not provided
        if not path_version_id:
            path_result = await self.db.execute(
                select(LearningPath).where(LearningPath.id == path_id)
            )
            path = path_result.scalar_one_or_none()
            path_version_id = path.active_version_id if path else None

        # Create or update unit content row
        version_id = str(uuid.uuid4())
        unit_content_id = existing.id if existing else str(uuid.uuid4())

        if not existing:
            from app.models.unit import LearningUnitContent as UnitContentModel

            uc = UnitContentModel(
                id=unit_content_id,
                user_id=user_id,
                path_id=path_id,
                path_version_id=path_version_id or "",
                node_id=node_id,
                status="generating",
            )
            self.db.add(uc)
            await self.db.flush()

        # Create generating version
        version = LearningUnitContentVersion(
            id=version_id,
            unit_content_id=unit_content_id,
            version_number=self._next_version_number(existing),
            status="generating",
            source="llm",
            quality_status="final",
        )
        self.db.add(version)
        await self.db.flush()

        # Enqueue task via enqueue_task (no commit)
        from app.services.task import TaskService

        task_service = TaskService(self.db)
        task = await task_service.enqueue_task(
            user_id=user_id,
            task_type="learning_unit_generation",
            target_type="node",
            target_id=node_id,
            target_metadata={"path_id": path_id, "unit_content_version_id": version_id},
        )

        # Update unit content with task info
        update_target = existing or uc  # type: ignore[possibly-undefined]
        update_target.active_task_id = task.id
        update_target.status = "generating"

        await self.db.commit()

        return {
            "next_step": "generating",
            "active_task_id": task.id,
            "unit_content_id": unit_content_id,
            "version_id": version_id,
        }

    async def regenerate_content(
        self,
        path_id: str,
        node_id: str,
        user_id: str,
        preferences: str | None = None,
    ) -> dict[str, object]:
        """Regenerate unit content preserving the existing active version."""
        from app.common.enums import TaskStatus
        from app.models.task import BackgroundTask
        from app.models.unit import LearningUnitContentVersion

        # Lock the unit content row
        existing = await self._ensure_unit_content(path_id, node_id, user_id, for_update=True)
        if not existing:
            raise ApiError(code="NO_CONTENT", message="Generate content first before regenerating", status_code=400)

        # Check for existing pending/running task
        if existing.active_task_id:
            task_result = await self.db.execute(
                select(BackgroundTask).where(
                    BackgroundTask.id == existing.active_task_id,
                    BackgroundTask.status.in_([TaskStatus.PENDING.value, TaskStatus.RUNNING.value]),
                )
            )
            active_task = task_result.scalar_one_or_none()
            if active_task:
                return {"next_step": "generating", "active_task_id": active_task.id}

        # Create new generating version (keep existing active_version_id)
        version_id = str(uuid.uuid4())
        version = LearningUnitContentVersion(
            id=version_id,
            unit_content_id=existing.id,
            version_number=self._next_version_number(existing),
            status="generating",
            source="llm",
            quality_status="final",
        )
        self.db.add(version)
        await self.db.flush()

        # Enqueue task
        from app.services.task import TaskService

        task_service = TaskService(self.db)
        metadata: dict[str, Any] = {"path_id": path_id, "unit_content_version_id": version_id}
        if preferences:
            metadata["preferences"] = preferences

        task = await task_service.enqueue_task(
            user_id=user_id,
            task_type="learning_unit_generation",
            target_type="node",
            target_id=node_id,
            target_metadata=metadata,
        )

        # Update unit content
        existing.active_task_id = task.id
        existing.status = "regenerating"

        await self.db.commit()

        return {"next_step": "generating", "active_task_id": task.id, "version_id": version_id}

    @staticmethod
    def _next_version_number(content: LearningUnitContent | None) -> int:
        """Determine the next version number."""
        if not content or not content.versions:
            return 1
        return max(v.version_number for v in content.versions) + 1

    async def get_mind_map(
        self,
        path_id: str,
        node_id: str,
        user_id: str,
    ) -> dict[str, object]:
        """Generate a mind map tree from existing unit content.

        Returns a hierarchical tree structure and Mermaid markdown.
        Does NOT use LLM — derived deterministically from content.
        """
        from sqlalchemy.orm import selectinload

        result = await self.db.execute(
            select(LearningUnitContent)
            .options(selectinload(LearningUnitContent.versions))
            .where(
                LearningUnitContent.path_id == path_id,
                LearningUnitContent.node_id == node_id,
                LearningUnitContent.user_id == user_id,
            )
        )
        content = result.scalar_one_or_none()
        if not content:
            raise ApiError(code="CONTENT_NOT_FOUND", message="No content found for this node", status_code=404)

        # Get content data from active version or legacy
        if content.active_version_id and content.versions:
            active_version = next(
                (v for v in content.versions if v.id == content.active_version_id), None
            )
            content_data = active_version.content if active_version and active_version.content else (content.content or {})
        else:
            content_data = content.content or {}

        title = content_data.get("introduction", "").strip("# \n").split("\n")[0] if content_data.get("introduction") else "未知节点"
        objectives = content_data.get("objectives", [])
        sections = content_data.get("sections", [])

        # Build hierarchical tree
        tree: list[dict[str, object]] = [
            {"id": "root", "label": title, "children": []}
        ]

        # Objectives branch
        obj_branch: dict[str, object] = {"id": "objectives", "label": "学习目标", "children": []}
        for i, obj in enumerate(objectives):
            obj_branch["children"].append({"id": f"obj-{i}", "label": obj, "children": []})
        if objectives:
            tree[0]["children"].append(obj_branch)

        # Sections branch
        for sec in sections:
            sec_title = sec.get("title", "未命名章节")
            sec_branch: dict[str, object] = {
                "id": f"sec-{sec.get('order', 0)}",
                "label": sec_title,
                "children": [],
            }
            tree[0]["children"].append(sec_branch)

        # Generate Mermaid mindmap
        mermaid_lines = ["mindmap", f"  root(({title}))"]
        if objectives:
            mermaid_lines.append("    学习目标")
            for obj in objectives:
                mermaid_lines.append(f"      {obj[:60]}")
        for sec in sections:
            sec_title = sec.get("title", "章节")
            mermaid_lines.append(f"     {sec_title}")
            # Extract key points from section content (first line)
            sec_content = sec.get("content", "")
            first_line = sec_content.split("\n")[0].strip("# *")[:60] if sec_content else ""
            if first_line:
                mermaid_lines.append(f"      {first_line}")

        return {
            "tree": tree,
            "mermaid": "\n".join(mermaid_lines),
            "node_id": node_id,
        }

    async def generate_quiz_bank(
        self,
        path_id: str,
        node_id: str,
        user_id: str,
    ) -> dict[str, object]:
        """Start a quiz bank generation task."""
        from app.services.task import TaskService

        task_service = TaskService(self.db)
        task = await task_service.create_task(
            user_id=user_id,
            task_type="learning_assessment_generation",
            target_type="node",
            target_id=node_id,
            target_metadata={"path_id": path_id},
        )
        return {"next_step": "generating", "active_task_id": task.id}

    async def create_assessment(
        self,
        path_id: str,
        node_id: str,
        user_id: str,
    ) -> dict[str, object]:
        """Create an assessment with 10+ questions for a node."""
        # Check if assessment already exists
        result = await self.db.execute(
            select(Assessment).where(
                Assessment.path_id == path_id,
                Assessment.node_id == node_id,
                Assessment.user_id == user_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return await self._format_assessment(existing)

        # Look up node context for question generation
        from app.models.path import LearningNode

        node_result = await self.db.execute(select(LearningNode).where(LearningNode.id == node_id))
        node = node_result.scalar_one_or_none()
        title = node.title if node else "本知识点"
        outcomes_raw = node.learning_outcomes if node else "[]"
        outcomes = json.loads(outcomes_raw) if isinstance(outcomes_raw, str) else (outcomes_raw or [])

        # Create assessment
        assessment = Assessment(
            id=str(uuid.uuid4()),
            user_id=user_id,
            path_id=path_id,
            path_version_id="",
            node_id=node_id,
            status="pending",
        )
        self.db.add(assessment)
        await self.db.flush()

        # Try LLM generation, fall back to template
        questions_data = await self._llm_generate_questions(title, outcomes, is_assessment=True)
        for idx, qd in enumerate(questions_data):
            q = AssessmentQuestion(
                id=str(uuid.uuid4()),
                assessment_id=assessment.id,
                question_type=qd["type"],
                prompt=qd["prompt"],
                options=json.dumps(qd.get("options")) if qd.get("options") else None,
                correct_answer=qd.get("correct_answer", ""),
                points=qd.get("points", 1),
                question_order=idx + 1,
            )
            self.db.add(q)

        await self.db.commit()
        return await self._format_assessment(assessment)

    async def create_practice(
        self,
        path_id: str,
        node_id: str,
        user_id: str,
    ) -> dict[str, object]:
        """Create a practice question set (not persisted, repeatable)."""
        from app.models.path import LearningNode

        node_result = await self.db.execute(select(LearningNode).where(LearningNode.id == node_id))
        node = node_result.scalar_one_or_none()
        title = node.title if node else "本知识点"
        outcomes_raw = node.learning_outcomes if node else "[]"
        outcomes = json.loads(outcomes_raw) if isinstance(outcomes_raw, str) else (outcomes_raw or [])

        questions_data = await self._llm_generate_questions(title, outcomes, is_assessment=False)
        return {
            "node_id": node_id,
            "questions": [
                {
                    "question_id": f"practice-{idx + 1}",
                    "type": q["type"],
                    "prompt": q["prompt"],
                    "options": q.get("options"),
                    "correct_answer": q.get("correct_answer", ""),
                }
                for idx, q in enumerate(questions_data)
            ],
        }

    async def _llm_generate_questions(self, title: str, outcomes: list[str], is_assessment: bool) -> list[dict]:
        """Generate questions via LLM, falling back to templates."""
        from app.services.llm import LLMError, llm_json

        count = "10-12" if is_assessment else "5"
        kind = "通关评估" if is_assessment else "练习"

        system_prompt = f"""你是一个专业的教育评估设计智能体。你的任务是为学习节点生成{kind}题目。

要求：
1. 生成 {count} 道题
2. 题型分布：单选题占 60%，多选题占 20%，简答题占 20%
3. 题目必须考察对知识点的真实理解，不能是"以下哪个说法正确"这种泛化题目
4. 单选题和多选题的选项必须具体、有区分度
5. 每道题的 prompt（题干）必须完整、清晰

请以 JSON 格式输出：
{{
  "questions": [
    {{
      "type": "single_choice",
      "prompt": "完整的题目描述",
      "options": [
        {{"value": "a", "label": "具体选项A"}},
        {{"value": "b", "label": "具体选项B"}},
        {{"value": "c", "label": "具体选项C"}},
        {{"value": "d", "label": "具体选项D"}}
      ],
      "correct_answer": "a",
      "points": 1
    }},
    {{
      "type": "multiple_choice",
      "prompt": "完整的题目描述（多选）",
      "options": [
        {{"value": "a", "label": "选项A"}},
        {{"value": "b", "label": "选项B"}},
        {{"value": "c", "label": "选项C"}},
        {{"value": "d", "label": "选项D"}}
      ],
      "correct_answer": "[\\"a\\", \\"b\\", \\"c\\"]",
      "points": 2
    }},
    {{
      "type": "short_answer",
      "prompt": "开放性问题描述",
      "correct_answer": "",
      "points": 3
    }}
  ]
}}"""

        outcomes_text = "\n".join(f"- {o}" for o in outcomes) if outcomes else "（无具体学习目标）"
        user_msg = f"""请为以下学习节点生成{kind}题目：

节点标题：{title}
学习目标：
{outcomes_text}

要求：
- 生成 {count} 道题
- 题目内容必须与「{title}」直接相关
- 单选题 4 个选项，多选题 4 个选项
- 简答题的 correct_answer 设为空字符串"""

        try:
            result = await llm_json(system_prompt, user_msg, temperature=0.4, max_tokens=4096)
            questions: list[dict[Any, Any]] = result.get("questions", [])
            if len(questions) >= (10 if is_assessment else 5):
                return questions
        except (LLMError, Exception):
            pass

        # Fallback to templates
        if is_assessment:
            return self._generate_assessment_questions(title, outcomes)
        return self._generate_practice_questions(title, outcomes)

    def _generate_assessment_questions(self, title: str, outcomes: list[str]) -> list[dict[Any, Any]]:
        """Generate 10 assessment questions based on node context."""
        o1 = outcomes[0] if len(outcomes) > 0 else f"{title}的基本概念"
        o2 = outcomes[1] if len(outcomes) > 1 else f"{title}的实际应用"
        questions: list[dict[Any, Any]] = [
            {
                "type": "single_choice",
                "points": 1,
                "prompt": f"关于「{title}」，以下哪个描述最准确？",
                "options": [
                    {"value": "a", "label": f"{title}是一种基础概念，广泛应用于实际开发中"},
                    {"value": "b", "label": f"{title}仅适用于特定场景，不具有通用性"},
                    {"value": "c", "label": f"{title}已经过时，不建议学习"},
                    {"value": "d", "label": f"{title}只涉及理论，与实践无关"},
                ],
                "correct_answer": "a",
            },
            {
                "type": "single_choice",
                "points": 1,
                "prompt": f"学习「{title}」的首要目标是什么？",
                "options": [
                    {"value": "a", "label": "记忆所有相关定义和术语"},
                    {"value": "b", "label": o1},
                    {"value": "c", "label": "跳过基础直接学习高级内容"},
                    {"value": "d", "label": "仅阅读文档即可，无需实践"},
                ],
                "correct_answer": "b",
            },
            {
                "type": "single_choice",
                "points": 1,
                "prompt": f"在使用「{title}」时，以下哪种做法是推荐的？",
                "options": [
                    {"value": "a", "label": "直接复制粘贴代码，不做理解"},
                    {"value": "b", "label": "忽略错误处理，快速实现功能"},
                    {"value": "c", "label": "先理解原理，再结合实际场景应用"},
                    {"value": "d", "label": "只看教程视频，不动手编码"},
                ],
                "correct_answer": "c",
            },
            {
                "type": "single_choice",
                "points": 1,
                "prompt": f"「{title}」在实际项目中的主要价值体现在哪里？",
                "options": [
                    {"value": "a", "label": "增加代码复杂度以显示技术水平"},
                    {"value": "b", "label": f"掌握{o2}，提高开发效率和代码质量"},
                    {"value": "c", "label": "仅用于面试中回答问题"},
                    {"value": "d", "label": "没有任何实际价值"},
                ],
                "correct_answer": "b",
            },
            {
                "type": "single_choice",
                "points": 1,
                "prompt": f"关于「{title}」的学习路径，以下哪种方式最有效？",
                "options": [
                    {"value": "a", "label": "直接学习高级内容，遇到问题再回看基础"},
                    {"value": "b", "label": "只阅读官方文档，不做任何练习"},
                    {"value": "c", "label": "先掌握基础概念，再通过练习巩固，最后应用到实际项目"},
                    {"value": "d", "label": "一次性学习所有内容，不做复习"},
                ],
                "correct_answer": "c",
            },
            {
                "type": "single_choice",
                "points": 1,
                "prompt": f"在调试「{title}」相关代码时，应该首先关注什么？",
                "options": [
                    {"value": "a", "label": "直接重写所有代码"},
                    {"value": "b", "label": "检查输入输出是否符合预期，定位问题范围"},
                    {"value": "c", "label": "忽略错误信息，随机尝试修改"},
                    {"value": "d", "label": "等待他人帮助，不做任何排查"},
                ],
                "correct_answer": "b",
            },
            {
                "type": "multiple_choice",
                "points": 2,
                "prompt": f"以下哪些是学习「{title}」时需要掌握的关键技能？（多选）",
                "options": [
                    {"value": "a", "label": o1},
                    {"value": "b", "label": "理解基本原理和概念"},
                    {"value": "c", "label": "能够进行实际应用和编码"},
                    {"value": "d", "label": "记忆所有历史版本的变更日志"},
                ],
                "correct_answer": json.dumps(["a", "b", "c"]),
            },
            {
                "type": "multiple_choice",
                "points": 2,
                "prompt": f"在项目中应用「{title}」时，以下哪些是好的实践？（多选）",
                "options": [
                    {"value": "a", "label": "编写清晰的文档和注释"},
                    {"value": "b", "label": "进行充分的测试"},
                    {"value": "c", "label": "考虑代码的可维护性和扩展性"},
                    {"value": "d", "label": "忽略代码规范，追求快速完成"},
                ],
                "correct_answer": json.dumps(["a", "b", "c"]),
            },
            {
                "type": "short_answer",
                "points": 3,
                "prompt": f"请用自己的话简要说明「{title}」的核心概念，以及它在实际开发中的一个应用场景。",
                "correct_answer": "",
            },
            {
                "type": "short_answer",
                "points": 3,
                "prompt": f"在学习「{title}」的过程中，你遇到了哪些困难？你是如何解决的？请举一个具体的例子。",
                "correct_answer": "",
            },
            {
                "type": "single_choice",
                "points": 1,
                "prompt": f"「{title}」的难度级别属于哪个层次？",
                "options": [
                    {"value": "a", "label": "完全不需要任何基础知识"},
                    {"value": "b", "label": "需要一定的前置知识和实践经验"},
                    {"value": "c", "label": "只有专家才能理解"},
                    {"value": "d", "label": "无法通过学习掌握"},
                ],
                "correct_answer": "b",
            },
            {
                "type": "single_choice",
                "points": 1,
                "prompt": f"学习完「{title}」后，下一步最应该做什么？",
                "options": [
                    {"value": "a", "label": "立即学习完全不相关的其他领域"},
                    {"value": "b", "label": "通过实践项目巩固所学知识，然后继续学习后续节点"},
                    {"value": "c", "label": "停止学习，已经足够"},
                    {"value": "d", "label": "从头重新学习一遍"},
                ],
                "correct_answer": "b",
            },
        ]
        return questions

    def _generate_practice_questions(self, title: str, outcomes: list[str]) -> list[dict]:
        """Generate 5 practice questions (different from assessment)."""
        o1 = outcomes[0] if len(outcomes) > 0 else f"{title}的基本操作"
        return [
            {
                "type": "single_choice",
                "points": 1,
                "prompt": f"在使用「{title}」之前，首先需要确认什么？",
                "options": [
                    {"value": "a", "label": "开发环境和依赖是否已正确配置"},
                    {"value": "b", "label": "项目是否有足够多的代码行数"},
                    {"value": "c", "label": "是否使用了最新的框架版本"},
                    {"value": "d", "label": "以上都不是"},
                ],
                "correct_answer": "a",
            },
            {
                "type": "single_choice",
                "points": 1,
                "prompt": f"如果在使用「{title}」时遇到错误，最合理的排查步骤是？",
                "options": [
                    {"value": "a", "label": "重新安装所有依赖"},
                    {"value": "b", "label": "检查错误信息，定位出错的代码行和原因"},
                    {"value": "c", "label": "忽略错误继续开发"},
                    {"value": "d", "label": "删除项目重新开始"},
                ],
                "correct_answer": "b",
            },
            {
                "type": "multiple_choice",
                "points": 2,
                "prompt": f"以下哪些属于「{title}」的基本操作？（多选）",
                "options": [
                    {"value": "a", "label": o1},
                    {"value": "b", "label": "理解其基本原理和概念"},
                    {"value": "c", "label": "能够独立完成简单的相关任务"},
                    {"value": "d", "label": "背诵所有相关的技术规范文档"},
                ],
                "correct_answer": json.dumps(["a", "b", "c"]),
            },
            {
                "type": "short_answer",
                "points": 3,
                "prompt": f"请描述一个你会如何在实际项目中使用「{title}」的步骤。",
                "correct_answer": "",
            },
            {
                "type": "single_choice",
                "points": 1,
                "prompt": f"关于「{title}」的最佳学习方式，你认为是？",
                "options": [
                    {"value": "a", "label": "理论与实践相结合，边学边练"},
                    {"value": "b", "label": "只看文档不做练习"},
                    {"value": "c", "label": "只做练习不看文档"},
                    {"value": "d", "label": "等待别人教，自己不主动学习"},
                ],
                "correct_answer": "a",
            },
        ]

    async def submit_assessment(
        self,
        assessment_id: str,
        user_id: str,
        answers: dict[str, str | list[str]],
    ) -> dict:
        """Submit an assessment attempt."""
        # Get assessment
        result = await self.db.execute(
            select(Assessment).where(
                Assessment.id == assessment_id,
                Assessment.user_id == user_id,
            )
        )
        assessment = result.scalar_one_or_none()
        if not assessment:
            raise ApiError(code="ASSESSMENT_NOT_FOUND", message="Assessment not found", status_code=404)

        # Look up node title for LLM grading context
        from app.models.path import LearningNode

        node_result = await self.db.execute(select(LearningNode).where(LearningNode.id == assessment.node_id))
        node = node_result.scalar_one_or_none()
        node_title = node.title if node else "未知节点"

        # Get questions
        questions_result = await self.db.execute(
            select(AssessmentQuestion)
            .where(AssessmentQuestion.assessment_id == assessment_id)
            .order_by(AssessmentQuestion.question_order)
        )
        questions = list(questions_result.scalars().all())

        # Create attempt
        attempt = AssessmentAttempt(
            id=str(uuid.uuid4()),
            assessment_id=assessment_id,
            user_id=user_id,
            status="in_progress",
        )
        self.db.add(attempt)
        await self.db.flush()  # Flush so attempt.id is available for FK references

        # Grade answers
        total_points = 0
        earned_points = 0
        weak_concepts: list[str] = []
        explanations: dict[str, str] = {}

        # Grade answers — batch LLM call for short answers
        short_answer_pairs: list[tuple[int, str, str]] = []  # (idx, prompt, answer)
        for idx, question in enumerate(questions):
            total_points += question.points
            answer_value = answers.get(question.id)
            is_correct = False
            points_earned = 0
            feedback = ""

            if answer_value is not None:
                if question.question_type in ("single_choice", "multiple_choice"):
                    correct = question.correct_answer
                    if isinstance(answer_value, list):
                        is_correct = set(answer_value) == set(json.loads(correct) if correct else [])
                    else:
                        is_correct = str(answer_value) == str(correct)
                    if is_correct:
                        points_earned = question.points
                        earned_points += question.points
                    else:
                        weak_concepts.append(question.prompt[:50])
                        feedback = f"正确答案: {question.correct_answer}"
                elif question.question_type == "short_answer" and str(answer_value).strip():
                    short_answer_pairs.append((idx, question.prompt, str(answer_value)))
                    # Will be graded by LLM below; placeholder
                    continue

            # Save answer (non-short-answer)
            answer = AssessmentAnswer(
                id=str(uuid.uuid4()),
                attempt_id=attempt.id,
                question_id=question.id,
                answer_value=json.dumps(answer_value) if answer_value else None,
                is_correct=is_correct,
                points_earned=points_earned,
                feedback=feedback,
            )
            self.db.add(answer)

        # LLM-grade short answer questions in a single batch call
        grading_used_fallback = False
        if short_answer_pairs:
            short_feedback = await self._grade_short_answers(short_answer_pairs, node_title)
            for idx, _prompt, student_answer in short_answer_pairs:
                q = questions[idx]
                grade = short_feedback.get(idx, {"score": 0, "feedback": "未评分"})
                if grade.get("grading_status") == "provisional":
                    grading_used_fallback = True
                score_pct = grade.get("score", 0)
                is_correct = score_pct >= 60
                # Use int(x+0.5) instead of round() to avoid banker's rounding
                # which gives round(0.5)=0 and causes 1-point questions to score 0
                points_earned = max(0, int(q.points * score_pct / 100 + 0.5))
                earned_points += points_earned
                if not is_correct:
                    weak_concepts.append(q.prompt[:50])
                answer = AssessmentAnswer(
                    id=str(uuid.uuid4()),
                    attempt_id=attempt.id,
                    question_id=q.id,
                    answer_value=json.dumps(student_answer),
                    is_correct=is_correct,
                    points_earned=points_earned,
                    feedback=grade.get("feedback", ""),
                )
                self.db.add(answer)

        # Calculate score
        score = (earned_points / total_points * 100) if total_points > 0 else 0
        passed = score >= PASS_THRESHOLD

        # Update attempt
        attempt.submitted_at = utc_now()
        if grading_used_fallback:
            attempt.status = "provisional"
            attempt.score = score
            attempt.passed = False
            attempt.feedback = "部分简答题自动评分暂不可用，该结果为临时评分，暂不解锁后续节点及更新掌握度。"
            passed = False
        else:
            attempt.status = "scored"
            attempt.score = score
            attempt.passed = passed
            if passed:
                attempt.feedback = "恭喜通过！您已掌握本节点的核心知识。"
            else:
                attempt.feedback = await self._generate_remedial_feedback(assessment.node_id, weak_concepts, score)

        attempt.weak_concepts = weak_concepts
        attempt.explanations = explanations

        # Update assessment status
        assessment.status = "submitted"

        # Update mastery and progress only when not fallback
        if not grading_used_fallback:
            await self._update_mastery(user_id, assessment.node_id, score, passed, assessment_id)
            await self._update_progress(user_id, assessment.path_id, assessment.node_id, passed)

        # Update student profile dimensions (async, non-blocking)
        profile_result = None
        if not grading_used_fallback:
            try:
                from app.models.path import LearningNode
                from app.services.profile import ProfileService

                node_result = await self.db.execute(select(LearningNode).where(LearningNode.id == assessment.node_id))
                node = node_result.scalar_one_or_none()
                node_title = node.title if node else "未知节点"
                profile_svc = ProfileService(self.db)
                profile_result = await profile_svc.update_after_assessment(
                    user_id, node_title, score, passed, weak_concepts
                )
            except Exception:
                pass  # Profile update is non-critical

        await self.db.flush()
        await self.db.commit()

        submission_result: dict[str, Any] = {
            "score": score,
            "passed": passed,
            "feedback": attempt.feedback,
            "grading_status": "provisional" if grading_used_fallback else "completed",
            "mastery_delta": (score - 50 if passed else 0) if not grading_used_fallback else 0,
            "weak_concepts": weak_concepts,
            "explanations": explanations,
            "recommended_actions": ["重新学习本单元"] if not passed else [],
        }
        if profile_result:
            submission_result["profile_update"] = profile_result
        return submission_result

    async def _generate_remedial_feedback(self, node_id: str, weak_concepts: list[str], score: float) -> str:
        """Generate remedial feedback using LLM when assessment is failed."""
        from app.models.path import LearningNode
        from app.prompts.agents import REMEDIAL_SYSTEM, remedial_user
        from app.services.llm import LLMError, llm_json

        # Look up node title
        node_result = await self.db.execute(select(LearningNode).where(LearningNode.id == node_id))
        node = node_result.scalar_one_or_none()
        node_title = node.title if node else "本节点"

        try:
            result = await llm_json(
                REMEDIAL_SYSTEM,
                remedial_user(node_title, weak_concepts, score),
                temperature=0.5,
                max_tokens=1024,
            )
            # Format the remedial content into readable text
            parts = []
            for item in result.get("weak_analysis", []):
                parts.append(
                    f"📌 **{item.get('concept', '')}**\n原因：{item.get('reason', '')}\n建议：{item.get('suggestion', '')}"
                )
            actions = result.get("recommended_actions", [])
            if actions:
                parts.append("\n🎯 **推荐行动**\n" + "\n".join(f"- {a}" for a in actions))
            encouragement = result.get("encouragement", "")
            if encouragement:
                parts.append(f"\n💪 {encouragement}")
            return "\n\n".join(parts) if parts else f"评估未通过（得分：{score:.0f}/100），建议重新学习本单元内容。"
        except (LLMError, Exception):
            return f"评估未通过（得分：{score:.0f}/100）。薄弱环节：{'、'.join(weak_concepts) if weak_concepts else '多项知识点'}。建议重新学习本单元内容并完成练习题后再试。"

    async def _grade_short_answers(self, pairs: list[tuple[int, str, str]], node_title: str) -> dict[int, dict]:
        """Grade short answer questions in a single LLM call."""
        from app.services.llm import LLMError, llm_json

        # Map sequential LLM indices back to original question indices
        llm_to_orig = {i: orig_idx for i, (orig_idx, _, _) in enumerate(pairs)}
        questions_text = "\n\n".join(
            f"[题目{i}] {prompt}\n[学生答案] {answer}" for i, (_, prompt, answer) in enumerate(pairs)
        )

        system_prompt = """你是一个教育评估判分智能体。请对学生的简答题答案进行评分。

评分标准：
- 80-100分：答案准确、完整、有深度
- 60-79分：答案基本正确，但不够完整
- 40-59分：答案部分正确，有明显遗漏
- 0-39分：答案错误或过于简略

请以 JSON 格式输出每道题的评分，index 从 0 开始：
{
  "grades": [
    {"index": 0, "score": 75, "feedback": "具体评价和建议"}
  ]
}"""

        try:
            result = await llm_json(
                system_prompt,
                f"请对以下关于「{node_title}」的简答题答案进行评分：\n\n{questions_text}",
                temperature=0.2,
                max_tokens=2048,
            )
            grades = result.get("grades", [])
            return {
                llm_to_orig[g["index"]]: {"score": g.get("score", 0), "feedback": g.get("feedback", "")}
                for g in grades
                if "index" in g and g["index"] in llm_to_orig
            }
        except (LLMError, Exception):
            # Fallback: give 50 score and provisional fields/feedback
            return {
                idx: {
                    "score": 50,
                    "feedback": "自动评分暂不可用，该结果为临时评分。",
                    "grading_status": "provisional",
                    "grading_source": "fallback",
                }
                for idx, _, _ in pairs
            }

    async def _update_mastery(
        self,
        user_id: str,
        node_id: str,
        score: float,
        passed: bool,
        source_id: str,
    ) -> None:
        """Update mastery based on assessment result."""
        # Get current progress
        result = await self.db.execute(
            select(LearningProgress).where(
                LearningProgress.user_id == user_id,
                LearningProgress.node_id == node_id,
            )
        )
        progress = result.scalar_one_or_none()

        old_mastery = progress.mastery if progress else 0.0
        new_mastery = min(100.0, old_mastery + (score - 50) * 0.5) if passed else old_mastery

        # Update progress record
        if progress:
            progress.mastery = new_mastery

        # Create mastery snapshot
        snapshot = MasterySnapshot(
            id=str(uuid.uuid4()),
            user_id=user_id,
            node_id=node_id,
            old_mastery=old_mastery,
            new_mastery=new_mastery,
            evidence=f"Assessment score: {score}",
            source_type="assessment",
            source_id=source_id,
        )
        self.db.add(snapshot)

    async def _update_progress(
        self,
        user_id: str,
        path_id: str,
        node_id: str,
        passed: bool,
    ) -> None:
        """Update learning progress and unlock next nodes."""
        # Get or create progress
        result = await self.db.execute(
            select(LearningProgress).where(
                LearningProgress.user_id == user_id,
                LearningProgress.path_id == path_id,
                LearningProgress.node_id == node_id,
            )
        )
        progress = result.scalar_one_or_none()

        if not progress:
            progress = LearningProgress(
                id=str(uuid.uuid4()),
                user_id=user_id,
                path_id=path_id,
                node_id=node_id,
                status="in_progress",
                mastery=0.0,
                attempts=0,
            )
            self.db.add(progress)

        progress.attempts += 1

        if passed:
            progress.status = "completed"
            progress.completed_at = utc_now()

            # Unlock next nodes
            await self._unlock_next_nodes(user_id, path_id, node_id)

    async def _unlock_next_nodes(
        self,
        user_id: str,
        path_id: str,
        completed_node_id: str,
    ) -> None:
        """Unlock nodes whose prerequisites are all completed."""
        # Get active version for this path
        path_result = await self.db.execute(select(LearningPath).where(LearningPath.id == path_id))
        path = path_result.scalar_one_or_none()
        if not path or not path.active_version_id:
            return
        version_id = path.active_version_id

        # Get edges where completed node is source, filtered by version
        edges_result = await self.db.execute(
            select(LearningEdge).where(
                LearningEdge.source_node_id == completed_node_id,
                LearningEdge.version_id == version_id,
            )
        )
        outgoing_edges = list(edges_result.scalars().all())

        for edge in outgoing_edges:
            target_node_id = edge.target_node_id

            # Check all prerequisites of target node
            prereq_result = await self.db.execute(
                select(LearningEdge).where(
                    LearningEdge.target_node_id == target_node_id,
                    LearningEdge.version_id == version_id,
                )
            )
            prereq_edges = list(prereq_result.scalars().all())

            all_prereqs_met = True
            for prereq_edge in prereq_edges:
                prereq_progress = await self.db.execute(
                    select(LearningProgress).where(
                        LearningProgress.user_id == user_id,
                        LearningProgress.path_id == path_id,
                        LearningProgress.node_id == prereq_edge.source_node_id,
                    )
                )
                prereq = prereq_progress.scalar_one_or_none()
                if not prereq or prereq.status != "completed":
                    all_prereqs_met = False
                    break

            if all_prereqs_met:
                # Unlock target node
                target_progress = await self.db.execute(
                    select(LearningProgress).where(
                        LearningProgress.user_id == user_id,
                        LearningProgress.path_id == path_id,
                        LearningProgress.node_id == target_node_id,
                    )
                )
                progress = target_progress.scalar_one_or_none()
                if progress and progress.status == "locked":
                    progress.status = "available"
                elif not progress:
                    progress = LearningProgress(
                        id=str(uuid.uuid4()),
                        user_id=user_id,
                        path_id=path_id,
                        node_id=target_node_id,
                        status="available",
                    )
                    self.db.add(progress)

    async def _format_assessment(self, assessment: Assessment) -> dict:
        """Format assessment for API response."""
        questions_result = await self.db.execute(
            select(AssessmentQuestion)
            .where(AssessmentQuestion.assessment_id == assessment.id)
            .order_by(AssessmentQuestion.question_order)
        )
        questions = list(questions_result.scalars().all())

        return {
            "assessment_id": assessment.id,
            "path_id": assessment.path_id,
            "path_version": 1,
            "node_id": assessment.node_id,
            "status": assessment.status,
            "questions": [
                {
                    "question_id": q.id,
                    "type": q.question_type,
                    "prompt": q.prompt,
                    "options": json.loads(q.options)
                    if isinstance(q.options, str)
                    else (q.options if q.options else []),
                }
                for q in questions
            ],
            "saved_answers": {},
            "score": None,
            "mastery": None,
            "passed": None,
            "weak_concepts": [],
            "explanations": {},
            "recommended_actions": [],
        }
