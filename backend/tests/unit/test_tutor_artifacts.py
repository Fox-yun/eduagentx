"""Quality checks for structured tutor diagram, code, and animation artifacts."""

from __future__ import annotations

import pytest

from app.services.tutor import _build_code_example, _build_diagram, _build_storyboard, _select_diagram_type


def test_selection_diagram_explains_branch_mechanics() -> None:
    diagram = _build_diagram(
        "Python 核心概念",
        "我希望详细了解选择结构",
        "选择结构根据条件决定执行路径。",
    )

    labels = {node["label"] for node in diagram["nodes"]}
    assert {"条件表达式", "自上而下判断", "命中即停止", "边界值验证"}.issubset(labels)
    assert diagram["diagram_type"] == "concept_map"
    assert all(node.get("detail") for node in diagram["nodes"])
    assert all(edge.get("label") for edge in diagram["edges"])


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("列表和字典有什么区别", "comparison"),
        ("Python 数据类型有哪些分类", "hierarchy"),
        ("解释测试驱动开发的反馈闭环", "cycle"),
        ("选择结构如何执行", "flow"),
        ("什么是选择结构", "concept_map"),
    ],
)
def test_diagram_type_follows_semantic_relationship(question: str, expected: str) -> None:
    assert _select_diagram_type("Python 核心概念", question) == expected
    assert _build_diagram("Python 核心概念", question, "示例回答")["diagram_type"] == expected


def test_comparison_diagram_has_two_labeled_groups() -> None:
    diagram = _build_diagram("Python 容器", "列表和字典有什么区别", "二者的数据组织方式不同。")

    assert [group["label"] for group in diagram["groups"]] == ["列表", "字典"]
    assert {node.get("group") for node in diagram["nodes"] if node["kind"] == "concept"} == {"left", "right"}
    details = " ".join(node["detail"] for node in diagram["nodes"])
    assert "整数索引" in details
    assert "可哈希的键" in details
    assert "O(1)" in details


def test_selection_code_is_runnable_and_has_learning_scaffold() -> None:
    example = _build_code_example(
        "Python 核心概念",
        "请用代码解释 if elif else 选择结构",
        "选择结构会命中第一个成立的条件。",
    )

    compile(example["code"], "<tutor-example>", "exec")
    assert "def classify_score" in example["code"]
    assert "95 优秀" in example["expected_output"]
    assert len(example["walkthrough"]) >= 3
    assert "边界" in example["challenge"]


def test_storyboard_has_timed_concrete_scenes() -> None:
    storyboard = _build_storyboard(
        "Python 核心概念",
        "我希望详细了解选择结构",
        "选择结构根据条件决定执行路径。",
    )

    assert len(storyboard["scenes"]) == 5
    assert storyboard["estimated_seconds"] == sum(scene["duration_seconds"] for scene in storyboard["scenes"])
    assert all(scene["keywords"] for scene in storyboard["scenes"])
    assert any("临界值" in scene["narration"] for scene in storyboard["scenes"])
