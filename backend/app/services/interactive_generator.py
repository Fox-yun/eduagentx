"""AI-assisted generators for active-recall cards and case walkthroughs."""

from __future__ import annotations

import json
import re
from typing import Any

import structlog

from app.services.llm import LLMError, llm_json

logger = structlog.get_logger()

_CARD_TYPES = {"application", "misconception", "comparison", "prediction", "debugging", "concept"}
_DIFFICULTIES = {"easy", "medium", "hard"}


class InteractiveGenerator:
    """Generate learning interactions grounded in the canonical lecture."""

    @classmethod
    async def generate_cards_ai(cls, unit_content: dict[str, Any]) -> dict[str, Any]:
        """Generate scenario-based cards with a deterministic fallback."""
        fallback = cls.generate_cards(unit_content)
        try:
            payload = await llm_json(
                """你是主动回忆与迁移训练设计专家。只依据给定讲义生成学习卡片。
要求：
1. 生成 6-10 张卡片，至少覆盖应用判断、易错纠正、对比辨析、结果预测四类；
2. 正面必须给出具体情境、代码、现象或决策问题，禁止写“某章节核心是什么”“请回顾课程”；
3. 背面必须直接作答，说明判断依据或操作步骤，不能只是复述题目；
4. 每张卡片只考一个认知动作，答案 40-180 字；
5. 不引入讲义之外的事实。
只返回 JSON：{"title":字符串,"description":字符串,"items":[{"card_type":"application|misconception|comparison|prediction|debugging|concept","front":字符串,"back":字符串,"hint":字符串,"knowledge_point":字符串,"difficulty":"easy|medium|hard"}]}。""",
                f"讲义内容：\n{_source_excerpt(unit_content)}",
                temperature=0.35,
                max_tokens=5000,
            )
            return cls._normalize_cards(payload, fallback)
        except (LLMError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            logger.warning("interactive_cards_llm_fallback", error=str(exc))
            return fallback

    @classmethod
    async def generate_walkthrough_ai(cls, unit_content: dict[str, Any]) -> dict[str, Any]:
        """Generate one coherent case with consequential decision points."""
        fallback = cls.generate_walkthrough(unit_content)
        try:
            payload = await llm_json(
                """你是案例教学设计专家。把给定讲义转化为一个连续、真实、可操作的案例推演。
要求：
1. 先设定明确角色、任务、输入和成功标准，再给出 4-6 个连续步骤；
2. 每步描述必须推进同一个案例，包含当前已知信息或具体产物；
3. 思考题必须要求学习者作判断、找错误、预测结果或选择方案；
4. 参考答案要给出明确选择、依据和可检查结果，禁止“理解核心原理”“根据课程内容”等空话；
5. 最后一步必须产出可验证成果或验收清单；不引入讲义之外的事实。
只返回 JSON：{"title":字符串,"description":字符串,"items":[{"title":字符串,"description":字符串,"question":字符串,"expected_answer":字符串}]}。""",
                f"讲义内容：\n{_source_excerpt(unit_content)}",
                temperature=0.4,
                max_tokens=5000,
            )
            return cls._normalize_walkthrough(payload, fallback)
        except (LLMError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            logger.warning("walkthrough_llm_fallback", error=str(exc))
            return fallback

    @classmethod
    def generate_cards(cls, unit_content: dict[str, Any]) -> dict[str, Any]:
        """Create useful active-recall cards without an LLM."""
        title = _title(unit_content)
        sections = _sections(unit_content)
        cards: list[dict[str, Any]] = []

        for index, section in enumerate(sections[:5]):
            section_title = str(section.get("title") or f"知识点 {index + 1}")
            evidence = _meaningful_text(section.get("content")) or section_title
            cards.append(
                {
                    "id": f"card-apply-{index}",
                    "card_type": "application",
                    "front": f"你正在处理与“{section_title}”有关的任务。面对“{evidence[:72]}”这一条件，第一步应检查或执行什么？",
                    "back": f"先明确“{section_title}”的输入与目标，再按讲义中的规则处理：{evidence[:180]}。完成后用一个具体输入或结果检查是否符合该规则。",
                    "hint": "先找输入、规则和可验证结果",
                    "knowledge_point": section_title,
                    "difficulty": "medium",
                }
            )
            if index < 3:
                cards.append(
                    {
                        "id": f"card-error-{index}",
                        "card_type": "misconception",
                        "front": f"有人把“{section_title}”简化成“记住结论就可以，不必验证条件”。这个判断哪里有问题？",
                        "back": f"问题在于忽略了适用条件与验证步骤。讲义给出的有效依据是：{evidence[:180]}。正确做法是先确认条件，再执行并检查结果。",
                        "hint": "关注适用条件，而不是只背结论",
                        "knowledge_point": section_title,
                        "difficulty": "hard",
                    }
                )

        if not cards:
            objective = _first_text(unit_content.get("objectives")) or title
            summary = _meaningful_text(unit_content.get("summary")) or _meaningful_text(
                unit_content.get("introduction")
            )
            cards.append(
                {
                    "id": "card-concept-0",
                    "card_type": "concept",
                    "front": f"如果要证明自己已经达到“{objective}”，你会展示什么可检查的结果？",
                    "back": summary[:180] or f"应展示一个能够直接验证“{objective}”的操作结果，并说明使用的规则。",
                    "hint": "用可观察结果代替“我理解了”",
                    "knowledge_point": objective,
                    "difficulty": "medium",
                }
            )

        return {
            "title": f"{title} — 主动回忆卡片",
            "interactive_type": "cards",
            "description": f"围绕《{title}》的应用、易错点和结果验证生成的 {len(cards)} 张训练卡片。",
            "items": cards,
            "knowledge_points": list(dict.fromkeys(str(card["knowledge_point"]) for card in cards)),
            "estimated_minutes": max(5, len(cards) * 2),
            "generation_method": "structured_fallback",
        }

    @classmethod
    def generate_walkthrough(cls, unit_content: dict[str, Any]) -> dict[str, Any]:
        """Create one continuous case from sections without generic answers."""
        title = _title(unit_content)
        sections = _sections(unit_content)[:5]
        task = _practice_task(unit_content) or f"完成一个能够验证《{title}》核心知识的最小成果"
        items: list[dict[str, Any]] = []

        for index, section in enumerate(sections, 1):
            section_title = str(section.get("title") or f"步骤 {index}")
            evidence = _meaningful_text(section.get("content")) or section_title
            items.append(
                {
                    "step": index,
                    "title": f"{section_title}：形成第 {index} 个可检查结果",
                    "description": f"案例任务是“{task[:120]}”。当前需要把“{section_title}”转化为一次具体操作；讲义依据为：{evidence[:160]}",
                    "question": f"在继续下一步前，你会用什么输入、现象或产物证明“{section_title}”已经正确完成？",
                    "expected_answer": f"应先按“{evidence[:150]}”执行，再保留可观察的输入与输出；只有结果符合这条规则，才进入下一步。",
                }
            )

        if not items:
            items.append(
                {
                    "step": 1,
                    "title": "定义验收结果",
                    "description": f"你需要完成：{task[:160]}。先把目标改写成能够观察和检查的结果。",
                    "question": "最终要交付什么，怎样判断它正确？",
                    "expected_answer": f"交付物必须直接对应“{task[:120]}”，并包含输入、执行过程和结果三部分作为验收证据。",
                }
            )

        return {
            "title": f"{title} — 连贯案例实战",
            "interactive_type": "walkthrough",
            "description": f"围绕“{task[:100]}”逐步决策，每一步都要求给出可检查的结果。",
            "items": items,
            "generation_method": "structured_fallback",
        }

    @classmethod
    def _normalize_cards(cls, payload: Any, fallback: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ValueError("Card response must contain an items array")
        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(payload["items"][:10]):
            if not isinstance(item, dict):
                continue
            front = _plain(item.get("front"), 280)
            back = _plain(item.get("back"), 500)
            if len(front) < 12 or len(back) < 20 or _is_generic(back):
                continue
            card_type = str(item.get("card_type") or "application")
            difficulty = str(item.get("difficulty") or "medium")
            normalized.append(
                {
                    "id": f"card-ai-{index}",
                    "card_type": card_type if card_type in _CARD_TYPES else "application",
                    "front": front,
                    "back": back,
                    "hint": _plain(item.get("hint"), 120) or "先判断条件，再预测或验证结果",
                    "knowledge_point": _plain(item.get("knowledge_point"), 80) or "综合应用",
                    "difficulty": difficulty if difficulty in _DIFFICULTIES else "medium",
                }
            )
        if len(normalized) < 4:
            raise ValueError("Too few concrete cards returned")
        knowledge_points = list(dict.fromkeys(card["knowledge_point"] for card in normalized))
        return {
            "title": _plain(payload.get("title"), 120) or fallback["title"],
            "interactive_type": "cards",
            "description": _plain(payload.get("description"), 240) or fallback["description"],
            "items": normalized,
            "knowledge_points": knowledge_points,
            "estimated_minutes": max(6, len(normalized) * 2),
            "generation_method": "llm_grounded",
        }

    @classmethod
    def _normalize_walkthrough(cls, payload: Any, fallback: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ValueError("Walkthrough response must contain an items array")
        normalized: list[dict[str, Any]] = []
        for item in payload["items"][:6]:
            if not isinstance(item, dict):
                continue
            description = _plain(item.get("description"), 600)
            question = _plain(item.get("question"), 320)
            answer = _plain(item.get("expected_answer"), 600)
            if len(description) < 20 or len(question) < 12 or len(answer) < 25 or _is_generic(answer):
                continue
            normalized.append(
                {
                    "step": len(normalized) + 1,
                    "title": _plain(item.get("title"), 100) or f"案例步骤 {len(normalized) + 1}",
                    "description": description,
                    "question": question,
                    "expected_answer": answer,
                }
            )
        if len(normalized) < 3:
            raise ValueError("Too few concrete walkthrough steps returned")
        return {
            "title": _plain(payload.get("title"), 120) or fallback["title"],
            "interactive_type": "walkthrough",
            "description": _plain(payload.get("description"), 280) or fallback["description"],
            "items": normalized,
            "generation_method": "llm_grounded",
        }


def _source_excerpt(unit_content: dict[str, Any]) -> str:
    return json.dumps(unit_content, ensure_ascii=False, default=str)[:22_000]


def _title(unit_content: dict[str, Any]) -> str:
    introduction = _plain(unit_content.get("introduction"), 240).strip("# ")
    return introduction.splitlines()[0][:80] if introduction else "学习单元"


def _sections(unit_content: dict[str, Any]) -> list[dict[str, Any]]:
    value = unit_content.get("sections")
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _meaningful_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = re.sub(r"```[\s\S]*?```", "", value)
    for raw_line in text.splitlines():
        line = re.sub(r"^[#>*\-\d.\s]+", "", raw_line).replace("`", "").strip()
        if len(line) >= 18:
            return line[:220]
    return _plain(text, 220)


def _practice_task(unit_content: dict[str, Any]) -> str:
    tasks = unit_content.get("practice_tasks")
    if not isinstance(tasks, list) or not tasks:
        return ""
    task = tasks[0]
    if isinstance(task, dict):
        return _plain(task.get("description") or task.get("task") or task.get("title"), 220)
    return _plain(task, 220)


def _first_text(value: Any) -> str:
    if isinstance(value, list):
        return next((_plain(item, 160) for item in value if _plain(item, 160)), "")
    return _plain(value, 160)


def _plain(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value).strip()[:limit]


def _is_generic(text: str) -> bool:
    compact = text.replace(" ", "")
    patterns = ("请回顾课程", "根据课程内容", "理解核心原理", "正确应用相关知识", "结合所学知识")
    return any(pattern in compact for pattern in patterns)
