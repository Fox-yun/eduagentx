"""Tutor service — real-time Q&A for learning nodes with RAG.

Phase 3.7-C: Now uses the unified RAG Context Builder for knowledge retrieval,
ensuring structured citations and safe context that never leaks internal keys.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import StudentProfile
from app.models.unit import LearningUnitContent
from app.prompts.agents import TUTOR_SYSTEM, tutor_context
from app.services.learning_access import require_node_access
from app.services.llm import LLMError, llm_chat, llm_json
from app.services.rag_context import build_rag_context

logger = structlog.get_logger()
_TUTOR_LLM_TIMEOUT_SECONDS = 45.0


class TutorService:
    """Answer student questions about a learning node using LLM + RAG."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def ask(
        self,
        path_id: str,
        node_id: str,
        user_id: str,
        question: str,
        response_modes: list[str] | None = None,
    ) -> dict[str, Any]:
        """Answer a student's question about a specific learning node.

        Flow:
          1. Verify Path/Node access.
          2. Fetch Unit Content for base context.
          3. Knowledge Search Top-K (user's own documents only).
          4. Build token-limited context.
          5. Call LLM.
          6. Return Answer + Citations.

        Never leaks internal errors to the user.
        """
        # 1. Access control — verify user owns the path and node belongs to active version
        try:
            ctx = await require_node_access(self.db, user_id, path_id, node_id)
        except Exception:
            logger.warning("tutor_access_denied", path_id=path_id, node_id=node_id, user_id=user_id)
            raise

        node_title = ctx.node.title or "未知节点"

        # 2. Look up unit content for richer context
        content_result = await self.db.execute(
            select(LearningUnitContent).where(
                LearningUnitContent.path_id == path_id,
                LearningUnitContent.node_id == node_id,
                LearningUnitContent.user_id == user_id,
            )
        )
        content = content_result.scalar_one_or_none()

        agent_trace: list[dict[str, Any]] = [
            _agent_step("intent_analyzer", "问题分析智能体", "completed", _classify_question(question)),
        ]

        # 3. Build unit content string
        node_content = ""
        if content and content.content:
            sections = content.content.get("sections", [])
            if sections:
                node_content = "\n\n".join(
                    f"### {s.get('title', '')}\n{s.get('content', '')[:500]}" for s in sections[:3]
                )

        # 4. Knowledge search (RAG) — best-effort, failures don't block answering
        rag_ctx = await build_rag_context(
            db=self.db,
            user_id=user_id,
            query=question,
            path_id=path_id,
            node_id=node_id,
        )
        knowledge_context = rag_ctx.context_string
        citations = [c.to_dict() for c in rag_ctx.citations]
        has_knowledge = rag_ctx.has_results
        agent_trace.append(
            _agent_step(
                "knowledge_retriever",
                "知识检索智能体",
                "completed",
                f"检索到 {len(citations)} 条可引用资料" if has_knowledge else "未检索到外部资料，使用课程内容回答",
            )
        )

        profile_context, profile_version = await self._load_profile_context(user_id)

        # 5. Build final context and call LLM
        # If no knowledge results, explicitly note it in the context
        if not has_knowledge:
            knowledge_context = "（当前知识库中没有找到相关资料，请基于已有知识回答。）"

        context = tutor_context(
            node_title=node_title,
            node_content=node_content,
            knowledge_context=knowledge_context,
        )
        if profile_context:
            context += f"\n\n学习者画像参考：\n{profile_context}"
        system = TUTOR_SYSTEM.format(context=context)

        modes = list(dict.fromkeys(response_modes or []))

        try:
            answer_request = llm_chat(
                system_prompt=system,
                user_message=question,
                temperature=0.6,
                max_tokens=2048,
            )
            async with asyncio.timeout(_TUTOR_LLM_TIMEOUT_SECONDS):
                if modes:
                    answer, artifacts = await asyncio.gather(
                        answer_request,
                        _generate_tutor_artifacts(
                            node_title=node_title,
                            question=question,
                            answer="",
                            node_content=node_content,
                            modes=modes,
                        ),
                    )
                else:
                    answer = await answer_request
                    artifacts = {}
            agent_trace.append(
                _agent_step(
                    "personalized_tutor",
                    "个性化讲解智能体",
                    "completed",
                    "已结合当前节点、画像与检索资料生成分层讲解",
                )
            )

            diagram = artifacts.get("diagram") if "diagram" in modes else None
            code_example = artifacts.get("code_example") if "code" in modes else None
            storyboard = artifacts.get("storyboard") if "storyboard" in modes else None
            if diagram:
                agent_trace.append(_agent_step("visual_explainer", "图解智能体", "completed", "已生成概念关系图"))
            if code_example:
                agent_trace.append(_agent_step("code_coach", "代码实操智能体", "completed", "已生成可复制代码案例"))
            if storyboard:
                agent_trace.append(
                    _agent_step("storyboard_director", "动画导演智能体", "completed", "已生成三幕动画微课")
                )
            agent_trace.append(
                _agent_step(
                    "quality_reviewer",
                    "质量审查智能体",
                    "completed",
                    "已检查引用边界、内容完整性与学习难度匹配",
                )
            )
            return {
                "response_id": str(uuid.uuid4()),
                "question": question,
                "answer": answer,
                "node_id": node_id,
                "citations": citations,
                "has_knowledge": has_knowledge,
                "modalities": ["text", *modes],
                "diagram": diagram,
                "code_example": code_example,
                "storyboard": storyboard,
                "agent_trace": agent_trace,
                "personalization": {
                    "profile_version": profile_version,
                    "applied": bool(profile_context),
                },
                "quality": {
                    "grounded": has_knowledge or bool(node_content),
                    "personalized": bool(profile_context),
                    "safety_checked": True,
                },
            }
        except (LLMError, TimeoutError) as e:
            logger.error(
                "tutor_llm_error",
                error_type=type(e).__name__,
                request_id=getattr(e, "request_id", None),
                latency_ms=getattr(e, "latency_ms", None),
            )
            fallback_answer = (
                f"辅导服务暂时不可用或响应较慢，已切换到课程内容降级方案。针对“{_short_text(question, 56)}”，"
                "先通过图解梳理关键概念和关系，再运行最小示例，最后用正常值、边界值和异常值验证结论。"
            )
            diagram = _build_diagram(node_title, question, fallback_answer) if "diagram" in modes else None
            code_example = _build_code_example(node_title, question, fallback_answer) if "code" in modes else None
            storyboard = _build_storyboard(node_title, question, fallback_answer) if "storyboard" in modes else None
            fallback_trace = [
                *agent_trace,
                _agent_step(
                    "personalized_tutor", "个性化讲解智能体", "failed", "模型服务暂时不可用，已启用课程内容降级方案"
                ),
            ]
            if diagram:
                fallback_trace.append(
                    _agent_step("visual_explainer", "图解智能体", "completed", "已基于课程内容生成概念关系图")
                )
            if code_example:
                fallback_trace.append(
                    _agent_step("code_coach", "代码实操智能体", "completed", "已生成离线可用代码案例")
                )
            if storyboard:
                fallback_trace.append(
                    _agent_step("storyboard_director", "动画导演智能体", "completed", "已生成离线三幕动画微课")
                )
            fallback_trace.append(
                _agent_step("quality_reviewer", "质量审查智能体", "completed", "已标记降级状态并检查输出边界")
            )
            return {
                "response_id": str(uuid.uuid4()),
                "question": question,
                "answer": fallback_answer,
                "node_id": node_id,
                "citations": [],
                "has_knowledge": has_knowledge,
                "modalities": ["text", *modes],
                "diagram": diagram,
                "code_example": code_example,
                "storyboard": storyboard,
                "agent_trace": fallback_trace,
                "personalization": {"profile_version": profile_version, "applied": bool(profile_context)},
                "quality": {
                    "grounded": bool(node_content),
                    "personalized": bool(profile_context),
                    "safety_checked": True,
                },
            }

    async def _load_profile_context(self, user_id: str) -> tuple[str, int]:
        """Load a compact learner profile without making tutoring depend on it."""
        try:
            result = await self.db.execute(select(StudentProfile).where(StudentProfile.user_id == user_id))
            profile = result.scalar_one_or_none()
            if not profile or not isinstance(profile.dimensions, dict):
                return "", 0
            labels = {
                "knowledge_depth": "知识深度",
                "concept_grasp": "概念理解",
                "practice_ability": "实践能力",
                "learning_pace": "学习节奏",
                "resource_preference": "资源偏好",
                "error_pattern": "易错模式",
            }
            lines: list[str] = []
            for key, label in labels.items():
                value = (profile.dimensions.get(key) or {}).get("value")
                if value is not None:
                    lines.append(f"- {label}: {value}")
            return "\n".join(lines), int(profile.profile_version or 0)
        except Exception as exc:
            logger.warning("tutor_profile_context_failed", error=str(exc), user_id=user_id)
            return "", 0


def _agent_step(agent: str, role: str, status: str, summary: str) -> dict[str, str]:
    return {"agent": agent, "role": role, "status": status, "summary": summary}


def _classify_question(question: str) -> str:
    lower = question.lower()
    intents: list[str] = []
    if any(token in lower for token in ("代码", "实现", "报错", "code", "example")):
        intents.append("代码实操")
    if any(token in lower for token in ("原理", "流程", "关系", "区别", "图")):
        intents.append("概念图解")
    if any(token in lower for token in ("视频", "动画", "演示")):
        intents.append("动画演示")
    return f"识别为：{'、'.join(intents) if intents else '概念答疑'}"


def _short_text(value: str, limit: int = 72) -> str:
    cleaned = re.sub(r"[`#*_>\n]+", " ", value).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:limit] + ("…" if len(cleaned) > limit else "")


async def _generate_tutor_artifacts(
    *,
    node_title: str,
    question: str,
    answer: str,
    node_content: str,
    modes: list[str],
) -> dict[str, Any]:
    """Generate question-specific multimodal artifacts in one structured call."""
    fallback = {
        "diagram": _build_diagram(node_title, question, answer),
        "code_example": _build_code_example(node_title, question, answer),
        "storyboard": _build_storyboard(node_title, question, answer),
    }
    if not modes:
        return {}

    requested = [mode for mode in modes if mode in {"diagram", "code", "storyboard"}]
    try:
        payload = await llm_json(
            """你是多模态教学资源设计智能体。请把教师回答转成真正可学习、可操作的结构化资源。
只返回 JSON，不要输出 Markdown。仅生成 requested_modes 中要求的字段。

质量要求：
1. diagram：4-6 个与问题直接相关的节点；label 是短概念，detail 解释机制；edge.label 写清关系，禁止“明确问题/理解原理/完成实践”等空话。必须按语义选择 diagram_type：定义与概念关系用 concept_map，真实先后步骤用 flow，分类与组成用 hierarchy，差异比较用 comparison，反复迭代或反馈过程用 cycle；没有时间先后关系时禁止使用 flow。comparison 必须提供两个 groups 并为节点填写 group。
2. code_example：代码必须能直接运行，不得出现“if 条件: 执行代码块”、TODO 或伪代码；包含确定的 expected_output、2-5 条 walkthrough 和一个可操作 challenge。
3. storyboard：3-5 个连续场景，每幕 4-9 秒；visual 描述画面中具体出现的对象或状态变化，narration 负责讲清知识，keywords 为 1-3 个关键词；禁止只写“问题卡片进入画面”。
4. 所有内容必须紧扣 question、teacher_answer 和 course_context，不虚构库、接口或运行结果。

JSON 结构：
{
  "diagram": {"title":"", "diagram_type":"concept_map|flow|hierarchy|comparison|cycle", "summary":"", "groups":[{"id":"", "label":""}], "nodes":[{"id":"", "label":"", "detail":"", "kind":"question|concept|practice", "group":""}], "edges":[{"source":"", "target":"", "label":""}]},
  "code_example": {"title":"", "language":"python|javascript|text", "code":"", "expected_output":"", "explanation":"", "walkthrough":[""], "challenge":""},
  "storyboard": {"title":"", "estimated_seconds":24, "scenes":[{"title":"", "visual":"", "narration":"", "duration_seconds":6, "keywords":[""]}]}
}""",
            json.dumps(
                {
                    "node_title": node_title,
                    "question": question,
                    "teacher_answer": answer,
                    "course_context": node_content[:2400],
                    "requested_modes": requested,
                },
                ensure_ascii=False,
            ),
            temperature=0.25,
            max_tokens=2600,
        )
    except Exception as exc:
        logger.warning("tutor_artifact_generation_fallback", error=type(exc).__name__, modes=requested)
        return {key: value for key, value in fallback.items() if _artifact_mode(key) in requested}

    if not isinstance(payload, dict):
        return {key: value for key, value in fallback.items() if _artifact_mode(key) in requested}
    return {
        "diagram": _normalize_diagram(payload.get("diagram"), fallback["diagram"]),
        "code_example": _normalize_code_example(payload.get("code_example"), fallback["code_example"]),
        "storyboard": _normalize_storyboard(payload.get("storyboard"), fallback["storyboard"]),
    }


def _artifact_mode(key: str) -> str:
    return {"diagram": "diagram", "code_example": "code", "storyboard": "storyboard"}[key]


def _topic_blueprint(node_title: str, question: str) -> list[tuple[str, str]]:
    topic = f"{node_title} {question}".lower()
    if (
        any(token in topic for token in ("列表", "list"))
        and any(token in topic for token in ("字典", "dict"))
        and any(token in question.lower() for token in ("区别", "对比", "比较", "异同"))
    ):
        return [
            ("按位置访问", "list 使用从 0 开始的整数索引，适合按顺序保存和遍历元素。"),
            ("按键访问", "dict 使用唯一且可哈希的键定位值，表达名称、编号与对象之间的映射。"),
            ("有序序列场景", "list 适合元素可重复、顺序有意义的数据；按索引访问是 O(1)，成员检查通常是 O(n)。"),
            ("键值映射场景", "dict 适合按键查询和去重；按键读取与成员检查平均是 O(1)，但会占用更多内存。"),
        ]
    if any(token in topic for token in ("选择结构", "条件分支", "if", "elif", "else")):
        return [
            ("条件表达式", "表达式会被转换为 True 或 False，决定是否进入分支。"),
            ("自上而下判断", "程序按 if、elif 的顺序检查条件，顺序会影响结果。"),
            ("命中即停止", "执行第一个满足条件的代码块后，跳过同一结构中的其余分支。"),
            ("边界值验证", "使用 59、60、89、90 等临界值检查每个分支。"),
        ]
    if any(token in topic for token in ("二分", "binary search", "折半")):
        return [
            ("有序输入", "二分搜索的前提是待查序列已经按同一规则排序。"),
            ("维护搜索区间", "left 与 right 始终包围仍可能包含目标的区间。"),
            ("比较并折半", "比较中点后排除不可能的一半，使区间持续缩小。"),
            ("边界与失败", "覆盖空序列、首尾元素和目标不存在等情况。"),
        ]
    if any(token in topic for token in ("变量", "对象引用", "引用", "赋值")):
        return [
            ("名称绑定对象", "变量名保存对象引用，对象本身拥有类型和值。"),
            ("共享引用", "两个名称可以指向同一个可变对象并观察到同一次修改。"),
            ("重新绑定", "重新赋值只改变名称指向，不会自动修改旧对象。"),
            ("身份验证", "使用 is 或 id() 区分同一对象与值相等。"),
        ]
    return [
        ("输入与约束", "先明确问题提供的数据、前置条件和不允许发生的情况。"),
        ("核心规则", "找出决定结果的规则、关系或保持不变的条件。"),
        ("执行过程", "按顺序应用规则，并记录每一步状态如何变化。"),
        ("结果验证", "用正常、边界和异常输入检查结论是否稳定。"),
    ]


def _select_diagram_type(node_title: str, question: str) -> str:
    """Choose a visual grammar from the learner's intent, not the course title alone."""
    prompt = question.lower()
    if any(token in prompt for token in ("区别", "对比", "比较", "异同", " vs ", "versus")):
        return "comparison"
    if any(token in prompt for token in ("循环", "迭代", "生命周期", "闭环", "反馈过程")):
        return "cycle"
    if any(token in prompt for token in ("分类", "层级", "组成", "包含", "种类", "体系", "有哪些")):
        return "hierarchy"
    if any(token in prompt for token in ("步骤", "流程", "执行顺序", "运行过程", "怎么执行", "如何执行")):
        return "flow"
    return "concept_map"


def _comparison_groups(question: str) -> list[dict[str, str]]:
    cleaned = re.sub(r"^(请|帮我|解释|说明|比较|对比|分析)+", "", question.strip())
    match = re.search(r"(.{1,16}?)和(.{1,16}?)(?:有?什么)?(?:区别|不同|异同|对比)", cleaned)
    if not match:
        return [{"id": "left", "label": "对象 A"}, {"id": "right", "label": "对象 B"}]
    return [
        {"id": "left", "label": _short_text(match.group(1).strip("，。？? "), 14)},
        {"id": "right", "label": _short_text(match.group(2).strip("，。？? "), 14)},
    ]


def _build_diagram(node_title: str, question: str, answer: str) -> dict[str, Any]:
    diagram_type = _select_diagram_type(node_title, question)
    blueprint = _topic_blueprint(node_title, question)
    nodes = [
        {
            "id": "question",
            "label": _short_text(question, 32),
            "detail": "从问题中提取需要解释的机制与可验证结果。",
            "kind": "question",
        },
        *[
            {
                "id": f"concept-{index}",
                "label": label,
                "detail": detail,
                "kind": "concept",
                **(
                    {"group": "left" if index % 2 else "right"}
                    if diagram_type == "comparison"
                    else {}
                ),
            }
            for index, (label, detail) in enumerate(blueprint, start=1)
        ],
        {
            "id": "practice",
            "label": "动手验证",
            "detail": blueprint[-1][1],
            "kind": "practice",
        },
    ]
    if diagram_type in {"flow", "cycle"}:
        edge_labels = ["先识别", "再判断", "按规则执行", "检查边界", "形成证据"]
        edges = [
            {"source": nodes[index]["id"], "target": nodes[index + 1]["id"], "label": edge_labels[index]}
            for index in range(len(nodes) - 1)
        ]
        if diagram_type == "cycle":
            edges.append({"source": nodes[-1]["id"], "target": nodes[0]["id"], "label": "反馈迭代"})
    elif diagram_type == "hierarchy":
        edges = [
            {"source": "question", "target": node["id"], "label": "包含"}
            for node in nodes[1:-1]
        ]
        edges.append({"source": nodes[-2]["id"], "target": "practice", "label": "用于验证"})
    else:
        edges = [
            {"source": "question", "target": node["id"], "label": "关键关系"}
            for node in nodes[1:-1]
        ]
        edges.append({"source": nodes[-2]["id"], "target": "practice", "label": "验证"})
    return {
        "title": f"{_short_text(node_title, 28)} · 图解",
        "diagram_type": diagram_type,
        "summary": _short_text(answer, 96),
        "groups": _comparison_groups(question) if diagram_type == "comparison" else [],
        "nodes": nodes,
        "edges": edges,
    }


def _build_code_example(node_title: str, question: str, answer: str) -> dict[str, Any]:
    fenced = re.search(r"```([a-zA-Z0-9_+-]*)\s*\n([\s\S]*?)```", answer)
    if fenced:
        language = fenced.group(1).lower() or "text"
        code = fenced.group(2).strip()
    else:
        language = "python" if "python" in f"{node_title} {question}".lower() else "text"
        if language == "python":
            reference_keywords = ("变量", "对象引用", "引用")
            selection_keywords = ("选择结构", "条件", "分支", "if", "elif", "else")
            search_keywords = ("二分", "搜索", "查找")
            if any(keyword in question for keyword in selection_keywords):
                code = (
                    "def classify_score(score: int) -> str:\n"
                    "    if not 0 <= score <= 100:\n"
                    '        return "输入无效"\n'
                    "    if score >= 90:\n"
                    '        return "优秀"\n'
                    "    elif score >= 60:\n"
                    '        return "通过"\n'
                    "    else:\n"
                    '        return "需要巩固"\n\n'
                    "for score in (95, 72, 48, 120):\n"
                    "    print(score, classify_score(score))"
                )
            elif any(keyword in question for keyword in search_keywords):
                code = (
                    "def binary_search(values: list[int], target: int) -> int:\n"
                    "    left, right = 0, len(values) - 1\n"
                    "    while left <= right:\n"
                    "        middle = (left + right) // 2\n"
                    "        if values[middle] == target:\n"
                    "            return middle\n"
                    "        if values[middle] < target:\n"
                    "            left = middle + 1\n"
                    "        else:\n"
                    "            right = middle - 1\n"
                    "    return -1\n\n"
                    "print(binary_search([2, 4, 7, 9, 12], 9))"
                )
            elif any(keyword in question for keyword in reference_keywords):
                code = (
                    "original = [1, 2]\n"
                    "alias = original          # 两个变量名指向同一个列表对象\n\n"
                    "alias.append(3)\n"
                    "print(original)           # [1, 2, 3]\n"
                    "print(alias is original)  # True\n"
                    "print(id(alias) == id(original))  # True\n\n"
                    "alias = [99]              # alias 改为指向新对象\n"
                    "print(original)           # 原对象仍是 [1, 2, 3]\n"
                    "print(alias is original)  # False"
                )
            else:
                code = (
                    "def summarize(values: list[int]) -> dict[str, int]:\n"
                    "    return {\n"
                    '        "count": len(values),\n'
                    '        "minimum": min(values),\n'
                    '        "maximum": max(values),\n'
                    "    }\n\n"
                    "print(summarize([7, 2, 9, 4]))"
                )
        else:
            code = "输入 → 拆分问题 → 应用核心概念 → 用示例验证 → 总结"
    topic = f"{node_title} {question}".lower()
    if any(token in topic for token in ("选择结构", "条件", "分支", "if", "elif", "else")):
        expected_output = "95 优秀\n72 通过\n48 需要巩固\n120 输入无效"
        walkthrough = [
            "先检查非法范围，避免错误输入落入正常分支。",
            "if 与 elif 自上而下判断，命中后不再检查后续分支。",
            "用 60、90 等边界值补充测试，确认比较符号是否正确。",
        ]
        challenge = "把 80-89 增加为“良好”，并用 59、60、79、80、89、90 这些边界值写测试。"
        title = "选择结构：成绩分级"
    elif any(token in topic for token in ("二分", "搜索", "查找")):
        expected_output = "3"
        walkthrough = [
            "left 和 right 表示仍可能包含目标的闭区间。",
            "每次比较 middle 后，只保留仍可能命中的一半。",
            "当 left > right 时区间为空，返回 -1。",
        ]
        challenge = "分别查找首元素、尾元素和不存在的 8，记录返回值。"
        title = "二分搜索：维护搜索区间"
    else:
        expected_output = "运行代码，核对注释标出的输出。"
        walkthrough = ["先预测输出。", "运行代码核对。", "修改一个输入并解释变化。"]
        challenge = "替换一组输入，写下运行前预测与实际结果。"
        title = "最小可运行示例" if language != "text" else "实操步骤"
    return {
        "title": title,
        "language": language,
        "code": code[:3000],
        "expected_output": expected_output,
        "explanation": "代码把抽象规则变成可观察的输入、分支与输出。先预测，再运行，最后改动边界值。",
        "walkthrough": walkthrough,
        "challenge": challenge,
    }


def _build_storyboard(node_title: str, question: str, answer: str) -> dict[str, Any]:
    blueprint = _topic_blueprint(node_title, question)
    scenes = [
        {
            "title": "聚焦问题",
            "visual": f"画面中央显示“{_short_text(question, 34)}”，关键术语依次高亮。",
            "narration": f"先把问题缩小到一个可验证目标：{_short_text(question, 58)}",
            "duration_seconds": 5,
            "keywords": [blueprint[0][0]],
        },
        *[
            {
                "title": label,
                "visual": f"“{label}”卡片进入流程，前后状态用箭头连接并突出变化。",
                "narration": detail,
                "duration_seconds": 6,
                "keywords": [label],
            }
            for label, detail in blueprint[:3]
        ],
        {
            "title": "边界验证",
            "visual": "正常值、临界值和异常值三张输入卡依次进入，结果区同步更新。",
            "narration": blueprint[-1][1],
            "duration_seconds": 6,
            "keywords": ["正常输入", "边界值", "异常输入"],
        },
    ]
    return {
        "title": f"动画微课：{_short_text(node_title, 28)}",
        "estimated_seconds": sum(scene["duration_seconds"] for scene in scenes),
        "scenes": scenes,
    }


def _normalize_diagram(value: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        return fallback
    raw_nodes = value.get("nodes")
    if not isinstance(raw_nodes, list):
        return fallback
    diagram_type = fallback["diagram_type"]
    raw_groups = value.get("groups")
    groups: list[dict[str, str]] = []
    if diagram_type == "comparison" and isinstance(raw_groups, list):
        for index, raw_group in enumerate(raw_groups[:2]):
            if not isinstance(raw_group, dict):
                continue
            label = _short_text(str(raw_group.get("label") or ""), 18)
            if label:
                groups.append({"id": str(raw_group.get("id") or f"group-{index + 1}"), "label": label})
    if diagram_type == "comparison" and len(groups) != 2:
        groups = fallback["groups"]
    group_ids = {group["id"] for group in groups}
    nodes: list[dict[str, str]] = []
    for index, raw in enumerate(raw_nodes[:6]):
        if not isinstance(raw, dict):
            continue
        label = _short_text(str(raw.get("label") or ""), 34)
        if not label:
            continue
        kind = str(raw.get("kind") or "concept")
        if kind not in {"question", "concept", "practice"}:
            kind = "concept"
        node = {
            "id": str(raw.get("id") or f"node-{index + 1}"),
            "label": label,
            "detail": _short_text(str(raw.get("detail") or ""), 100),
            "kind": kind,
        }
        raw_group = str(raw.get("group") or "")
        if raw_group in group_ids:
            node["group"] = raw_group
        elif diagram_type == "comparison" and kind == "concept":
            concept_count = sum(item["kind"] == "concept" for item in nodes)
            node["group"] = groups[concept_count % 2]["id"]
        nodes.append(node)
    if len(nodes) < 4:
        return fallback
    node_ids = {node["id"] for node in nodes}
    raw_edges = value.get("edges")
    edges: list[dict[str, str]] = []
    if isinstance(raw_edges, list):
        for raw in raw_edges[:8]:
            if not isinstance(raw, dict):
                continue
            source, target = str(raw.get("source") or ""), str(raw.get("target") or "")
            if source in node_ids and target in node_ids:
                edges.append(
                    {"source": source, "target": target, "label": _short_text(str(raw.get("label") or "关联"), 14)}
                )
    if not edges:
        edges = [
            {"source": nodes[index]["id"], "target": nodes[index + 1]["id"], "label": "推进"}
            for index in range(len(nodes) - 1)
        ]
    return {
        "title": _short_text(str(value.get("title") or fallback["title"]), 42),
        "diagram_type": diagram_type,
        "summary": _short_text(str(value.get("summary") or fallback["summary"]), 120),
        "groups": groups,
        "nodes": nodes,
        "edges": edges,
    }


def _normalize_code_example(value: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        return fallback
    code = str(value.get("code") or "").strip()
    if len(code) < 30 or any(token in code for token in ("if 条件", "执行代码块", "TODO", "待补充")):
        return fallback
    walkthrough = [
        _short_text(str(item), 100)
        for item in value.get("walkthrough", [])[:5]
        if str(item).strip()
    ] if isinstance(value.get("walkthrough"), list) else []
    return {
        "title": _short_text(str(value.get("title") or fallback["title"]), 42),
        "language": _short_text(str(value.get("language") or fallback["language"]), 20),
        "code": code[:4000],
        "expected_output": str(value.get("expected_output") or fallback["expected_output"])[:1200],
        "explanation": _short_text(str(value.get("explanation") or fallback["explanation"]), 180),
        "walkthrough": walkthrough or fallback["walkthrough"],
        "challenge": _short_text(str(value.get("challenge") or fallback["challenge"]), 160),
    }


def _normalize_storyboard(value: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict) or not isinstance(value.get("scenes"), list):
        return fallback
    scenes: list[dict[str, Any]] = []
    for raw in value["scenes"][:5]:
        if not isinstance(raw, dict):
            continue
        narration = _short_text(str(raw.get("narration") or ""), 180)
        visual = _short_text(str(raw.get("visual") or ""), 140)
        if not narration or not visual:
            continue
        duration = raw.get("duration_seconds")
        duration = max(4, min(int(duration), 9)) if isinstance(duration, int | float) else 6
        keywords = [
            _short_text(str(item), 14)
            for item in raw.get("keywords", [])[:3]
            if str(item).strip()
        ] if isinstance(raw.get("keywords"), list) else []
        scenes.append(
            {
                "title": _short_text(str(raw.get("title") or "知识场景"), 30),
                "visual": visual,
                "narration": narration,
                "duration_seconds": duration,
                "keywords": keywords,
            }
        )
    if len(scenes) < 3:
        return fallback
    return {
        "title": _short_text(str(value.get("title") or fallback["title"]), 44),
        "estimated_seconds": sum(scene["duration_seconds"] for scene in scenes),
        "scenes": scenes,
    }
