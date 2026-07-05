"""Deterministic interactive resource generator.

Generates walkthrough and simulation resources from unit content
WITHOUT using LLM.
"""

from __future__ import annotations

import structlog
from typing import Any

logger = structlog.get_logger()


class InteractiveGenerator:
    """Deterministic interactive resource generator."""

    @classmethod
    def generate_cards(cls, unit_content: dict[str, Any]) -> dict[str, Any]:
        """Generate flip cards from unit content.

        Delegates to the existing get_interactive_cards logic in unit.py,
        but we replicate here for independence.
        """
        intro = unit_content.get("introduction", "").strip("# \n")
        title = intro.split("\n")[0] if intro else "未知节点"
        objectives = unit_content.get("objectives", [])
        sections = unit_content.get("sections", [])
        key_terms = unit_content.get("key_terms", [])
        practice_tasks = unit_content.get("practice_tasks", [])
        summary = unit_content.get("summary", "")

        cards: list[dict[str, Any]] = []

        # Concept cards from objectives
        for i, obj in enumerate(objectives):
            cards.append(
                {
                    "id": f"card-obj-{i}",
                    "card_type": "concept",
                    "front": f"学习目标：{obj}",
                    "back": f"请回顾《{title}》中关于「{obj}」的内容，确保你能够解释和应用这个概念。",
                    "hint": "查看对应章节的详细讲解",
                    "knowledge_point": obj,
                    "difficulty": "easy",
                }
            )

        # Key term cards
        if isinstance(key_terms, list):
            for i, term in enumerate(key_terms):
                if isinstance(term, dict):
                    term_name = term.get("term", term.get("name", f"术语 {i + 1}"))
                    term_def = term.get("definition", term.get("description", ""))
                elif isinstance(term, str):
                    term_name = term
                    term_def = ""
                else:
                    continue
                cards.append(
                    {
                        "id": f"card-term-{i}",
                        "card_type": "key_term",
                        "front": f"什么是「{term_name}」？",
                        "back": term_def or f"请回顾课程内容中关于「{term_name}」的定义和用法。",
                        "hint": f"在《{title}》中查找",
                        "knowledge_point": term_name,
                        "difficulty": "easy",
                    }
                )

        # Section concept cards
        for i, sec in enumerate(sections):
            sec_title = sec.get("title", f"章节 {i + 1}")
            sec_content = sec.get("content", "")
            first_sentence = ""
            for line in sec_content.split("\n"):
                clean = line.strip("# *-").strip()
                if len(clean) > 10:
                    first_sentence = clean[:200]
                    break
            if first_sentence:
                cards.append(
                    {
                        "id": f"card-sec-{i}",
                        "card_type": "concept",
                        "front": f"章节「{sec_title}」的核心要点是什么？",
                        "back": first_sentence,
                        "hint": f"参考《{title}》{sec_title}章节",
                        "knowledge_point": sec_title,
                        "difficulty": "medium",
                    }
                )

        # Practice task cards
        for i, task in enumerate(practice_tasks):
            if isinstance(task, dict):
                task_desc = task.get("description", task.get("task", str(task)))
            elif isinstance(task, str):
                task_desc = task
            else:
                continue
            cards.append(
                {
                    "id": f"card-practice-{i}",
                    "card_type": "practice",
                    "front": f"练习题：{task_desc[:100]}",
                    "back": "请尝试独立完成这道练习，然后对照课程内容检查你的答案。",
                    "hint": "结合所学知识点思考",
                    "knowledge_point": title,
                    "difficulty": "hard",
                }
            )

        # Summary card
        if summary:
            cards.append(
                {
                    "id": "card-summary",
                    "card_type": "summary",
                    "front": f"《{title}》的核心总结是什么？",
                    "back": summary[:300],
                    "hint": "回顾全部章节",
                    "knowledge_point": title,
                    "difficulty": "easy",
                }
            )

        return {
            "title": f"{title} — 交互式学习卡片",
            "interactive_type": "cards",
            "description": f"基于《{title}》课程内容自动生成的 {len(cards)} 张学习卡片，帮助巩固核心知识点。",
            "items": cards,
            "knowledge_points": list({c["knowledge_point"] for c in cards if c.get("knowledge_point")}),
            "estimated_minutes": max(5, len(cards) * 2),
        }

    @classmethod
    def generate_walkthrough(cls, unit_content: dict[str, Any]) -> dict[str, Any]:
        """Generate walkthrough (step-by-step case study) from unit content.

        Converts sections into a step-by-step walkthrough with questions.
        """
        intro = unit_content.get("introduction", "").strip("# \n")
        title = intro.split("\n")[0] if intro else "案例推演"
        sections = unit_content.get("sections", [])
        practice_tasks = unit_content.get("practice_tasks", [])

        items: list[dict[str, Any]] = []

        # Create walkthrough steps from sections
        for i, sec in enumerate(sections[:5], 1):
            sec_title = sec.get("title", f"步骤 {i}")
            sec_content = sec.get("content", "")

            # Extract description
            description = sec_title
            for line in sec_content.split("\n"):
                clean = line.strip("# *-").strip()
                if len(clean) > 20:
                    description = clean[:100]
                    break

            # Create a question
            question = f"在「{sec_title}」这个步骤中，最关键的是什么？"

            # Expected answer
            expected_answer = f"关键在于理解{sec_title}的核心原理并正确应用。"
            for line in sec_content.split("\n"):
                clean = line.strip("# *-").strip()
                if "关键" in clean or "重要" in clean or "必须" in clean:
                    expected_answer = clean[:150]
                    break

            items.append(
                {
                    "step": i,
                    "title": sec_title,
                    "description": description,
                    "question": question,
                    "expected_answer": expected_answer,
                }
            )

        # Add final practice step
        if practice_tasks:
            task = practice_tasks[0]
            if isinstance(task, dict):
                task_desc = task.get("description", task.get("task", str(task)))
            else:
                task_desc = str(task)

            items.append(
                {
                    "step": len(items) + 1,
                    "title": "实践任务",
                    "description": task_desc[:100],
                    "question": "请应用所学知识完成这个实践任务，并说明你的思路。",
                    "expected_answer": "根据课程内容，首先分析任务需求，然后应用相应知识点实现。",
                }
            )

        return {
            "title": f"{title} — 案例推演",
            "interactive_type": "walkthrough",
            "description": f"通过 {len(items)} 个步骤推演《{title}》的核心概念和实践流程。",
            "items": items,
        }

    @classmethod
    def generate_simulation(cls, unit_content: dict[str, Any]) -> dict[str, Any]:
        """Generate simulation (concept state transitions) from unit content.

        Creates a simulation of concept evolution with state changes.
        """
        intro = unit_content.get("introduction", "").strip("# \n")
        title = intro.split("\n")[0] if intro else "概念模拟"
        objectives = unit_content.get("objectives", [])
        sections = unit_content.get("sections", [])

        items: list[dict[str, Any]] = []

        # Initial state
        items.append(
            {
                "label": "初始状态",
                "state": {
                    "knowledge": objectives[0][:50] if objectives else "开始学习",
                    "mastery": 0.0,
                },
                "description": "学习开始前的状态。",
            }
        )

        # State transitions from sections
        cumulative_mastery = 0.0
        mastery_increment = 100.0 / max(len(sections), 1)

        for i, sec in enumerate(sections[:5], 1):
            sec_title = sec.get("title", f"阶段 {i}")
            cumulative_mastery += mastery_increment
            cumulative_mastery = min(cumulative_mastery, 100.0)

            # Extract knowledge point
            knowledge_point = sec_title
            sec_content = sec.get("content", "")
            for line in sec_content.split("\n"):
                clean = line.strip("# *-").strip()
                if len(clean) > 10 and len(clean) < 80:
                    knowledge_point = clean
                    break

            items.append(
                {
                    "label": f"阶段 {i}: {sec_title}",
                    "state": {
                        "knowledge": knowledge_point,
                        "mastery": round(cumulative_mastery, 1),
                    },
                    "description": f"学习「{sec_title}」后，知识点掌握度提升。",
                }
            )

        # Final state
        summary = unit_content.get("summary", "")
        items.append(
            {
                "label": "完成状态",
                "state": {
                    "knowledge": summary[:50] if summary else "学习完成",
                    "mastery": 100.0,
                },
                "description": "完成全部学习后的状态。",
            }
        )

        return {
            "title": f"{title} — 概念模拟",
            "interactive_type": "simulation",
            "description": f"模拟《{title}》学习过程中的 {len(items)} 个状态变化。",
            "items": items,
        }