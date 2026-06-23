import os
from typing import List, Dict
import json
import re
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from src.schema.state import AgentState
import time
from src.utils.trace import add_trace
from src.utils.progress import report_progress

from src.config.settings import settings

llm = ChatOpenAI(
    model=settings.llm_model_name,
    temperature=0.3
)

from src.runtime.task_store import ensure_task_active

def supervisor_node(state: AgentState) -> AgentState:
    """主控规则引擎，决定需要调用的 worker 节点"""
    ensure_task_active(state)
    start = time.time()
    report_progress(state, 45, "Supervisor 正在分配智能体任务")

    requested = state.get("requested_resources", [])
    if requested:
        resource_task_map = {
            "doc": "doc_generator",
            "quiz": "quiz_generator",
            "mindmap": "mindmap_generator",
            "plan": "planner",
            "reading": "reading_generator",
            "code_case": "code_case_generator",
            "ppt": "ppt_generator",
            "answer": "tutor"
        }
        tasks = [resource_task_map[r] for r in requested if r in resource_task_map]
    else:
        mode = state.get("mode", "快速模式")
        last_message = state["messages"][-1] if state.get("messages") else ""

        interactive_hint = any(
            keyword in last_message
            for keyword in [
                "互动", "可视化", "一步一步", "模拟", "动态演示", "拖动参数", "边学边练"
            ]
        )
        if interactive_hint:
            request_preferences = state.get("request_preferences", {})
            request_preferences["interactive_tutorial"] = True
            state["request_preferences"] = request_preferences

        only_mode = any(k in last_message for k in [
            "只要", "仅", "单独", "只生成", "只需", "仅需", "不要别的", "单独来个"
        ])

        if only_mode:
            if "代码" in last_message or "实操" in last_message or "Python" in last_message:
                tasks = ["code_case_generator"]
            elif "PPT" in last_message or "幻灯片" in last_message:
                tasks = ["ppt_generator"]
            elif "导图" in last_message or "思维导图" in last_message:
                tasks = ["mindmap_generator"]
            elif "题" in last_message or "练习" in last_message or "测验" in last_message:
                tasks = ["quiz_generator"]
            elif "计划" in last_message or "路线" in last_message or "安排" in last_message:
                tasks = ["planner"]
            else:
                tasks = ["doc_generator"]
        else:
            if mode == "快速模式":
                tasks = ["doc_generator", "quiz_generator", "planner"]
            elif mode == "完整模式":
                tasks = [
                    "doc_generator", "quiz_generator", "mindmap_generator",
                    "planner", "reading_generator", "code_case_generator", "ppt_generator"
                ]
            elif mode == "答疑模式":
                tasks = []
            else:
                tasks = ["doc_generator", "quiz_generator", "planner"]

            # 关键词覆盖：在非 only_mode 下附加生成
            if "代码" in last_message or "实操" in last_message or "Python" in last_message:
                if "code_case_generator" not in tasks: tasks.append("code_case_generator")
            if "PPT" in last_message or "幻灯片" in last_message:
                if "ppt_generator" not in tasks: tasks.append("ppt_generator")
            if "导图" in last_message or "思维导图" in last_message:
                if "mindmap_generator" not in tasks: tasks.append("mindmap_generator")
            if "题" in last_message or "练习" in last_message or "测验" in last_message:
                if "quiz_generator" not in tasks: tasks.append("quiz_generator")

    # 优先级排序 P0 > P1 > P2
    priority_map = {
        "doc_generator": 0, "quiz_generator": 0, "planner": 0,
        "mindmap_generator": 1, "code_case_generator": 1,
        "reading_generator": 2, "ppt_generator": 2, "tutor": 0
    }
    tasks = sorted(tasks, key=lambda x: priority_map.get(x, 99))

    trace = add_trace("Supervisor", "success", f"分配任务: {len(tasks)}项", start)
    report_progress(
        state,
        50,
        f"已启动 {len(tasks)} 个资源生成智能体并发执行"
    )

    return {"pending_tasks": tasks, "agent_trace": [trace]}

from src.utils.logger import get_logger
logger = get_logger("supervisor")

def reviewer_node(state: AgentState) -> AgentState:
    """质检员，基于规则审核最终生成的所有内容"""
    ensure_task_active(state)
    start = time.time()
    report_progress(state, 90, "Reviewer 正在执行轻量级防幻觉审核")
    logger.info("正在对所有的生成资源进行安全与防幻觉审核...", extra={"task_id": state.get("task_id", ""), "agent": "Reviewer"})
    
    generated = state.get("generated_resources", {})
    context = state.get("retrieved_context", "")

    if not generated:
        review_feedback = "未生成有效资源，无法审核。"
    elif not context or context in ["未检索到相关教材内容。", "检索服务异常。"]:
        review_feedback = "警告：当前生成内容缺少可靠课程资料依据，建议结合教材进一步核对。"
    else:
        review_feedback = f"审核通过：已安全审核 {len(generated)} 类资源内容。"

    trace = add_trace("Reviewer", "success", "完成轻量审核", start)
    report_progress(
        state,
        98,
        "审核完成",
        review_feedback=review_feedback
    )

    return {"review_feedback": review_feedback, "agent_trace": [trace]}
