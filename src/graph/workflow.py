from langgraph.graph import StateGraph, END
from src.schema.state import AgentState
from src.agents.diagnostic_group import profiler_node, diagnoser_node, router_node
from src.agents.supervisor import supervisor_node, reviewer_node
from src.agents.worker_group import (
    doc_generator_node, 
    quiz_generator_node, 
    mindmap_generator_node, 
    planner_node, 
    reading_generator_node,
    code_case_generator_node,
    ppt_generator_node,
    tutor_node,
    evaluator_node,
    remedial_tutor_node
)

from langgraph.types import Send

def task_router(state: AgentState):
    """动态路由：并发分发给所有需要的 Worker 节点"""
    tasks = state.get("pending_tasks", [])
    if not tasks:
        return "reviewer"
    return [Send(task, state) for task in tasks]

def build_graph():
    # 声明状态图
    workflow = StateGraph(AgentState)
    
    # 1. 注册所有的节点
    workflow.add_node("profiler", profiler_node)
    workflow.add_node("diagnoser", diagnoser_node)
    
    # 新增主管与审核
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("reviewer", reviewer_node)
    
    # 注册生成器员工
    workflow.add_node("doc_generator", doc_generator_node)
    workflow.add_node("quiz_generator", quiz_generator_node)
    workflow.add_node("mindmap_generator", mindmap_generator_node)
    workflow.add_node("planner", planner_node)
    workflow.add_node("reading_generator", reading_generator_node)
    workflow.add_node("code_case_generator", code_case_generator_node)
    workflow.add_node("ppt_generator", ppt_generator_node)
    
    workflow.add_node("tutor", tutor_node)
    
    workflow.add_node("evaluator", evaluator_node)
    workflow.add_node("remedial_tutor", remedial_tutor_node)
    
    # 2. 定义流程图的边
    workflow.set_entry_point("profiler")
    workflow.add_edge("profiler", "diagnoser")
    
    # Diagnoser 结束后，判断是走大模型流水线还是简单的答疑
    workflow.add_conditional_edges(
        "diagnoser",
        router_node,
        {
            "want_to_learn": "supervisor",     # 学习需求交给主管分配任务
            "want_to_practice": "supervisor",  # 练习需求也交给主管分配任务
            "want_to_ask": "tutor",            # 单纯答疑直接走 tutor
            "want_to_evaluate": "evaluator"    # 提交答案触发评估
        }
    )
    
    routing_map = {
        "doc_generator": "doc_generator",
        "quiz_generator": "quiz_generator",
        "mindmap_generator": "mindmap_generator",
        "planner": "planner",
        "reading_generator": "reading_generator",
        "code_case_generator": "code_case_generator",
        "ppt_generator": "ppt_generator",
        "reviewer": "reviewer"
    }
    
    workflow.add_conditional_edges("supervisor", task_router, routing_map)
    
    for node in [
        "doc_generator",
        "quiz_generator",
        "mindmap_generator",
        "planner",
        "reading_generator",
        "code_case_generator",
        "ppt_generator",
    ]:
        workflow.add_edge(node, "reviewer")
        
    workflow.add_edge("evaluator", "remedial_tutor")
    workflow.add_edge("remedial_tutor", "reviewer")
    
    # 最终的审核节点完成后，流向结束
    workflow.add_edge("reviewer", END)
    workflow.add_edge("tutor", END)
    
    # 3. 编译运行APP
    return workflow.compile()
