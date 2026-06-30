"""Unit tests for prompt template functions."""

from app.prompts.agents import (
    assessment_designer_system,
    assessment_designer_user,
    content_generator_user,
    path_planner_user,
    profiler_user,
    remedial_user,
    reviewer_user,
    tutor_context,
)


class TestPathPlannerPrompts:
    def test_basic_goal(self):
        result = path_planner_user("学习 Python 编程")
        assert "Python 编程" in result
        assert "5-15" in result

    def test_with_all_fields(self):
        result = path_planner_user("机器学习", "从零开始", "beginner", "intermediate")
        assert "机器学习" in result
        assert "从零开始" in result
        assert "beginner" in result
        assert "intermediate" in result

    def test_minimal_goal(self):
        result = path_planner_user("数据结构")
        assert "数据结构" in result


class TestContentGeneratorPrompts:
    def test_basic_content_prompt(self):
        result = content_generator_user("Python 列表", "学习列表操作", "beginner", ["掌握列表方法"])
        assert "Python 列表" in result
        assert "列表操作" in result
        assert "beginner" in result
        assert "掌握列表方法" in result

    def test_with_goal_title(self):
        result = content_generator_user("DFS", "深度优先", "intermediate", ["理解DFS"], goal_title="算法学习")
        assert "算法学习" in result


class TestAssessmentDesignerPrompts:
    def test_system_prompt_contains_count(self):
        result = assessment_designer_system("10-12", "通关评估")
        assert "10-12" in result
        assert "通关评估" in result

    def test_user_prompt_contains_title(self):
        result = assessment_designer_user("二叉树遍历", ["前序遍历", "中序遍历"], "10-12", "通关评估")
        assert "二叉树遍历" in result
        assert "前序遍历" in result


class TestTutorPrompts:
    def test_context_with_title_only(self):
        result = tutor_context("Python 基础")
        assert "Python 基础" in result

    def test_context_with_content(self):
        result = tutor_context("DFS", "## 概念\n深度优先搜索...")
        assert "DFS" in result
        assert "深度优先搜索" in result

    def test_context_truncates_long_content(self):
        long_content = "x" * 5000
        result = tutor_context("topic", long_content)
        assert len(result) < 3000


class TestRemedialPrompts:
    def test_basic_remedial(self):
        result = remedial_user("二叉树", ["前序遍历"], 45.0)
        assert "二叉树" in result
        assert "45" in result
        assert "前序遍历" in result


class TestReviewerPrompts:
    def test_reviewer_user(self):
        sections = [{"title": "概念介绍", "content": "这是内容"}]
        result = reviewer_user("DFS", sections)
        assert "DFS" in result
        assert "概念介绍" in result


class TestProfilerPrompts:
    def test_profiler_passed(self):
        result = profiler_user("Python", 85.0, True, [], {"knowledge_depth": 60})
        assert "85" in result
        assert "通过" in result
        assert "knowledge_depth" in result

    def test_profiler_failed(self):
        result = profiler_user("DFS", 40.0, False, ["前序遍历"])
        assert "40" in result
        assert "未通过" in result
        assert "前序遍历" in result

    def test_profiler_no_current_dimensions(self):
        result = profiler_user("topic", 70.0, True, [])
        assert "70" in result
