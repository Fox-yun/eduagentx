"""Deterministic quality review for generated learning resources.

The reviewer intentionally exposes concise, auditable checks instead of hidden
reasoning.  Its output is stored with every resource so clients can explain why
an artifact is considered ready or needs review.
"""

from __future__ import annotations

from typing import Any

QUALITY_PASS_SCORE = 70


def evaluate_resource_quality(
    resource_type: str,
    unit_content: dict[str, Any],
    resource_content: dict[str, Any],
) -> dict[str, Any]:
    """Score a generated resource on a stable 100-point rubric."""
    dimensions = [
        _content_completeness(unit_content),
        _learning_design(resource_type, unit_content, resource_content),
        _usability(resource_type, resource_content),
        _course_alignment(resource_type, unit_content, resource_content),
        _safety(resource_type, resource_content),
    ]
    score = sum(item["score"] for item in dimensions)
    warnings = [item["recommendation"] for item in dimensions if item["score"] < item["max_score"] * 0.7]
    grade = (
        "excellent"
        if score >= 90
        else "good"
        if score >= 80
        else "acceptable"
        if score >= QUALITY_PASS_SCORE
        else "needs_review"
    )
    return {
        "score": score,
        "max_score": 100,
        "grade": grade,
        "passed": score >= QUALITY_PASS_SCORE,
        "threshold": QUALITY_PASS_SCORE,
        "dimensions": dimensions,
        "warnings": warnings,
        "reviewer": "resource_quality_reviewer",
        "rubric_version": "1.1",
    }


def _dimension(
    key: str,
    label: str,
    score: int,
    max_score: int,
    summary: str,
    recommendation: str,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "score": min(max(score, 0), max_score),
        "max_score": max_score,
        "summary": summary,
        "recommendation": recommendation,
    }


def _content_completeness(unit_content: dict[str, Any]) -> dict[str, Any]:
    objectives = _list(unit_content.get("objectives"))
    sections = _list(unit_content.get("sections"))
    score = 0
    score += 5 if _text(unit_content.get("introduction")) else 0
    score += 5 if len(objectives) >= 2 else 2 if objectives else 0
    score += 10 if len(sections) >= 3 else len(sections) * 3
    score += 5 if _text(unit_content.get("summary")) else 0
    return _dimension(
        "completeness",
        "课程内容完整度",
        score,
        25,
        f"检测到 {len(objectives)} 个目标、{len(sections)} 个章节。",
        "补充学习目标、至少三个有效章节和单元总结。",
    )


def _learning_design(
    resource_type: str,
    unit_content: dict[str, Any],
    resource_content: dict[str, Any],
) -> dict[str, Any]:
    tasks = _list(unit_content.get("practice_tasks"))
    items = _list(resource_content.get("items"))
    files = [str(item) for item in _list(resource_content.get("files"))]
    score = 8 if tasks else 0

    if resource_type == "pptx":
        count = _number(resource_content.get("slide_count"))
        score += 17 if count >= 6 else 13 if count >= 4 else 7 if count >= 2 else 0
        summary = f"包含 {count} 页课件，课程实践任务 {'已覆盖' if tasks else '未覆盖'}。"
    elif resource_type == "code_zip":
        has_readme = "README.md" in files
        has_source = any(name.endswith((".py", ".js", ".ts", ".java")) for name in files)
        has_test = any("test" in name.lower() for name in files)
        score += (6 if has_readme else 0) + (6 if has_source else 0) + (5 if has_test else 0)
        summary = f"README、源码、测试覆盖：{has_readme}/{has_source}/{has_test}。"
    elif resource_type == "interactive_cards":
        difficulties = {str(item.get("difficulty")) for item in items if isinstance(item, dict)}
        card_types = {str(item.get("card_type")) for item in items if isinstance(item, dict)}
        concrete = sum(
            1
            for item in items
            if isinstance(item, dict)
            and not _is_generic(_text(item.get("front")))
            and not _is_generic(_text(item.get("back")))
        )
        score += 8 if len(items) >= 6 else 5 if len(items) >= 4 else len(items)
        score += 5 if len(card_types) >= 3 else 3 if len(card_types) >= 2 else 0
        score += 4 if concrete == len(items) and items else 2 if concrete >= max(len(items) // 2, 1) else 0
        summary = (
            f"包含 {len(items)} 张卡片、{len(difficulties)} 个难度层次、"
            f"{len(card_types)} 类认知任务，{concrete} 张通过具体性检查。"
        )
    elif resource_type == "walkthrough":
        complete_steps = sum(
            1
            for item in items
            if isinstance(item, dict) and _text(item.get("question")) and _text(item.get("expected_answer"))
        )
        concrete_answers = sum(
            1
            for item in items
            if isinstance(item, dict) and not _is_generic(_text(item.get("expected_answer")))
        )
        score += 8 if len(items) >= 4 else 5 if len(items) >= 3 else len(items)
        score += 4 if complete_steps == len(items) and items else 2 if complete_steps else 0
        score += 5 if concrete_answers == len(items) and items else 2 if concrete_answers else 0
        summary = (
            f"包含 {len(items)} 个连续步骤，{complete_steps} 个带问题和答案，"
            f"{concrete_answers} 个答案通过具体性检查。"
        )
    elif resource_type == "narrated_video":
        slide_count = _number(resource_content.get("slide_count"))
        has_captions = _text(resource_content.get("captions_vtt")).startswith("WEBVTT")
        has_voice = bool(_text(resource_content.get("tts_model")) and _text(resource_content.get("tts_voice")))
        score += 10 if slide_count >= 5 else 6 if slide_count >= 3 else slide_count
        score += 4 if has_captions else 0
        score += 3 if has_voice else 0
        summary = f"包含 {slide_count} 个画面，字幕与语音配置：{has_captions}/{has_voice}。"
    else:
        summary = "资源类型未配置专项教学设计检查。"

    return _dimension(
        "learning_design",
        "教学设计",
        score,
        25,
        summary,
        "增加分层内容、实践任务或带反馈的学习环节。",
    )


def _usability(resource_type: str, resource_content: dict[str, Any]) -> dict[str, Any]:
    score = 5 if _text(resource_content.get("title")) else 0
    if resource_type in {"pptx", "code_zip", "narrated_video"}:
        count_key = "file_count" if resource_type == "code_zip" else "slide_count"
        count = _number(resource_content.get(count_key))
        score += 10 if count >= 3 else 6 if count >= 1 else 0
    else:
        items = _list(resource_content.get("items"))
        score += 10 if len(items) >= 3 else len(items) * 3
    score += 5 if _text(resource_content.get("description")) else 0
    return _dimension(
        "usability",
        "可用性",
        score,
        20,
        "检查标题、内容数量和使用说明。",
        "补充清晰标题、使用说明和足够的可操作内容。",
    )


def _course_alignment(
    resource_type: str,
    unit_content: dict[str, Any],
    resource_content: dict[str, Any],
) -> dict[str, Any]:
    sections = _list(unit_content.get("sections"))
    target_count = max(len(sections), 1)
    if resource_type in {"pptx", "narrated_video"}:
        covered = max(_number(resource_content.get("slide_count")) - 2, 0)
    elif resource_type == "code_zip":
        covered = len(_list(resource_content.get("files")))
    else:
        covered = len(_list(resource_content.get("items")))
    ratio = min(covered / target_count, 1.0)
    score = round(20 * ratio)
    return _dimension(
        "alignment",
        "课程对齐度",
        score,
        20,
        f"资源容量覆盖约 {round(ratio * 100)}% 的章节规模。",
        "让资源条目覆盖更多课程章节和学习目标。",
    )


def _safety(resource_type: str, resource_content: dict[str, Any]) -> dict[str, Any]:
    score = 10
    summary = "资源为结构化只读内容。"
    if resource_type == "code_zip":
        files = [str(item).lower() for item in _list(resource_content.get("files"))]
        forbidden = (".exe", ".dll", ".bat", ".cmd", ".ps1", ".sh")
        unsafe = [name for name in files if name.endswith(forbidden)]
        score = 0 if unsafe else 10
        summary = "未发现可执行脚本或二进制危险扩展。" if not unsafe else f"发现风险文件：{', '.join(unsafe)}"
    return _dimension(
        "safety",
        "安全与边界",
        score,
        10,
        summary,
        "移除危险文件或不可控执行入口。",
    )


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _number(value: Any) -> int:
    return int(value) if isinstance(value, (int, float)) else 0


def _is_generic(text: str) -> bool:
    compact = text.replace(" ", "")
    return any(
        phrase in compact
        for phrase in ("请回顾课程", "根据课程内容", "理解核心原理", "正确应用相关知识", "结合所学知识")
    )
