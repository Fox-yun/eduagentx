import os
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from src.schema.state import AgentState
import time
from src.utils.trace import add_trace
from src.utils.progress import report_progress

from src.utils.logger import get_logger
from src.utils.structured_output import invoke_structured
from src.schemas.quiz import QuizResourceSchema, QuizItemSchema
from src.schemas.plan import LearningPlanSchema

from src.config.settings import settings
from src.utils.llm_semaphore import safe_invoke

logger = get_logger("worker_group")

from src.runtime.task_store import (
    ensure_task_can_continue, task_heartbeat_guard,
    TaskCancelledError, TaskExpiredError, TaskAlreadyFinishedError, TaskStateConflictError
)

TASK_CONTROL_EXCEPTIONS = (
    TaskCancelledError,
    TaskExpiredError,
    TaskAlreadyFinishedError,
    TaskStateConflictError,
)

def save_generated_resource(
    state: AgentState,
    *,
    progress: int,
    stage: str,
    resource_delta: dict,
    trace: dict | None = None,
) -> None:
    task_id = state.get("task_id")
    if not task_id:
        return

    ensure_task_can_continue(task_id)

    saved = report_progress(
        state,
        progress,
        stage,
        generated_resources=resource_delta,
        agent_trace=[trace] if trace else None,
    )

    if not saved:
        ensure_task_can_continue(task_id)
        raise TaskStateConflictError(f"任务 {task_id} 已不允许写入资源")

llm = ChatOpenAI(
    model=settings.llm_model_name, 
    temperature=settings.llm_temperature
)

def should_generate_tutorial_widgets(mode: str, user_input: str, request_preferences: dict) -> bool:
    if mode == "答疑模式":
        return False
    if request_preferences.get("interactive_tutorial"):
        return True
    keywords = [
        "互动", "可视化", "分步骤", "一步一步",
        "边学边练", "即时练习", "模拟过程"
    ]
    if any(k in user_input for k in keywords):
        return True
    return mode == "完整模式"

def doc_generator_node(state: AgentState) -> AgentState:
    """真实调用大模型，生成适应基础的教学文档及互动教程组件"""
    task_id = state.get("task_id", "")
    ensure_task_can_continue(task_id)
    
    start = time.time()
    report_progress(state, 55, "Doc Generator 正在生成课程讲义")
    logger.info("正在根据画像动态生成定制化文档...", extra={"task_id": state.get("task_id", ""), "agent": "DocGenerator"})
    
    profile = state.get("student_profile", {})
    prefs = state.get("request_preferences", {})
    effective_profile = {**profile, **prefs}
    last_message = state["messages"][-1] if state["messages"] else "未提供具体需求"
    
    retrieved_context = state.get("retrieved_context", "无参考资料")
    
    mode = state.get("mode", "快速模式")
    if mode == "快速模式":
        length_requirement = "控制在 300-500 字，重点清晰，便于快速理解。"
    else:
        length_requirement = "内容可以更详细，但避免无意义重复，控制在 800 字以内。"
        
    from src.prompts.generators import DOC_GENERATOR_PROMPT
    prompt = ChatPromptTemplate.from_template(DOC_GENERATOR_PROMPT)
    
    chain = prompt | llm

    ensure_task_can_continue(task_id)
    try:
        with task_heartbeat_guard(task_id):
            result = safe_invoke(chain, {
                "context": retrieved_context,
                "major": effective_profile.get("major", "未知"),
                "foundation": effective_profile.get("foundation", "未知"),
                "cognitive_style": effective_profile.get("cognitive_style", "未知"),
                "learning_goal": effective_profile.get("learning_goal", "未知"),
                "input": last_message,
                "length_requirement": length_requirement
            })
        markdown = result.content
        doc_trace = add_trace("DocGenerator", "success", "完成讲义正文生成", start)
        doc_resource = {
            "type": "document",
            "status": "completed",
            "format": "markdown",
            "title": "课程讲义",
            "data": {"content": markdown}
        }
        resource_delta = {"doc": doc_resource}
        save_generated_resource(state, progress=57, stage="课程讲义已生成", resource_delta=resource_delta, trace=doc_trace)

        # Stage 2: 互动教程生成
        doc_widgets = []
        tutorial_trace = None
        widgets_resource = None

        if should_generate_tutorial_widgets(mode, last_message, prefs):
            report_progress(state, 58, "Doc Generator 正在生成互动教程配置")
            from src.schemas.tutorial_widget import InteractiveTutorialSchema
            from src.prompts.tutorial_widgets import tutorial_widgets_prompt
            
            tutorial_start = time.time()
            ensure_task_can_continue(task_id)
            try:
                with task_heartbeat_guard(task_id):
                    tutorial = invoke_structured(
                        llm=llm,
                        prompt=tutorial_widgets_prompt,
                        schema=InteractiveTutorialSchema,
                        fallback=InteractiveTutorialSchema(),
                        task_id=task_id,
                        agent_name="TutorialDesigner",
                        input_kwargs={
                            "user_input": last_message,
                            "student_profile": effective_profile,
                            "request_preferences": prefs,
                            "markdown": markdown[:8000],
                        },
                    )
                
                doc_widgets = [widget.model_dump() for widget in tutorial.widgets]
                tutorial_trace = add_trace("TutorialDesigner", "success", f"生成了 {len(doc_widgets)} 个互动组件", tutorial_start)
                widgets_resource = {
                    "type": "tutorial_widgets",
                    "status": "completed",
                    "format": "json",
                    "title": "互动教程",
                    "data": {"widgets": doc_widgets}
                }
                save_generated_resource(state, progress=60, stage=f"讲义互动组件已生成，共 {len(doc_widgets)} 个", resource_delta={"doc_widgets": widgets_resource}, trace=tutorial_trace)
            except TASK_CONTROL_EXCEPTIONS:
                raise
            except Exception as e:
                logger.exception("互动配置生成失败", extra={"task_id": task_id, "agent": "TutorialDesigner"})
                tutorial_trace = add_trace("TutorialDesigner", "warning", f"互动组件生成失败，已保留普通讲义: {e}", tutorial_start)

        ensure_task_can_continue(task_id)
        final_traces = [doc_trace]
        if tutorial_trace:
            final_traces.append(tutorial_trace)

        final_resources = {"doc": doc_resource}
        if widgets_resource is not None:
            final_resources["doc_widgets"] = widgets_resource

        return {
            "generated_resources": final_resources,
            "agent_trace": final_traces
        }
    except TASK_CONTROL_EXCEPTIONS:
        raise
    except Exception as e:
        logger.exception("生成失败", extra={"task_id": state.get("task_id", ""), "agent": "DocGenerator"})
        trace = add_trace("DocGenerator", "failed", f"讲义生成失败: {e}", start)
        error_resource = {
            "type": "document",
            "status": "failed",
            "format": "markdown",
            "title": "课程讲义",
            "data": {},
            "error": str(e)
        }
        return {"generated_resources": {"doc": error_resource}, "agent_trace": [trace]}

def quiz_generator_node(state: AgentState) -> AgentState:
    """根据检索内容和画像，生成针对性测试题"""
    task_id = state.get("task_id", "")
    ensure_task_can_continue(task_id)

    start = time.time()
    report_progress(state, 60, "Quiz Generator 正在生成练习题")
    logger.info("正在根据 RAG 知识库出题...", extra={"task_id": state.get("task_id", ""), "agent": "QuizGenerator"})
    profile = state.get("student_profile", {})
    prefs = state.get("request_preferences", {})
    effective_profile = {**profile, **prefs}
    retrieved_context = state.get("retrieved_context", "无参考资料")
    
    from src.prompts.generators import QUIZ_GENERATION_PROMPT
    prompt = ChatPromptTemplate.from_template(QUIZ_GENERATION_PROMPT)
    
    fallback_quiz = QuizResourceSchema(
        quizzes=[
            QuizItemSchema(
                type="essay",
                question="练习题生成失败，请稍后重试。",
                answer="无",
                explanation="模型响应异常"
            )
        ]
    )
    
    ensure_task_can_continue(task_id)
    try:
        with task_heartbeat_guard(task_id):
            validated = invoke_structured(
                llm=llm,
                prompt=prompt,
                schema=QuizResourceSchema,
                fallback=fallback_quiz,
                task_id=task_id,
                agent_name="QuizGenerator",
                input_kwargs={"foundation": effective_profile.get("foundation", "未知"), "context": retrieved_context}
            )
        
        trace = add_trace("QuizGenerator", "success", "完成题库生成", start)
        quiz_resource = {
            "type": "quiz",
            "status": "completed",
            "format": "json",
            "title": "随堂测验",
            "data": validated.model_dump()
        }
        resource_delta = {"quiz": quiz_resource}
        save_generated_resource(state, progress=65, stage="练习题库已生成", resource_delta=resource_delta, trace=trace)
        return {"generated_resources": resource_delta, "agent_trace": [trace]}
    except TASK_CONTROL_EXCEPTIONS:
        raise
    except Exception as e:
        logger.exception("出题失败", extra={"task_id": state.get("task_id", ""), "agent": "QuizGenerator"})
        trace = add_trace("QuizGenerator", "failed", f"题库生成异常: {e}", start)
        error_resource = {
            "type": "quiz",
            "status": "failed",
            "format": "json",
            "title": "随堂测验",
            "data": {},
            "error": str(e)
        }
        return {
            "generated_resources": {"quiz": error_resource}, 
            "agent_trace": [trace]
        }

def mindmap_generator_node(state: AgentState) -> AgentState:
    """将检索到的知识转化为思维导图"""
    task_id = state.get("task_id", "")
    ensure_task_can_continue(task_id)

    start = time.time()
    report_progress(state, 65, "Mindmap Generator 正在生成思维导图")
    logger.info("正在生成思维导图 Mermaid 结构...", extra={"task_id": state.get("task_id", ""), "agent": "MindmapGenerator"})
    retrieved_context = state.get("retrieved_context", "无参考资料")
    
    from src.prompts.generators import MINDMAP_GENERATION_PROMPT
    prompt = ChatPromptTemplate.from_template(MINDMAP_GENERATION_PROMPT)
    chain = prompt | llm
    
    ensure_task_can_continue(task_id)
    try:
        with task_heartbeat_guard(task_id):
            res = safe_invoke(chain, {"context": retrieved_context})
        trace = add_trace("MindmapGenerator", "success", "完成导图生成", start)
        mindmap_resource = {
            "type": "mindmap",
            "status": "completed",
            "format": "mermaid",
            "title": "思维导图",
            "data": {"content": res.content}
        }
        resource_delta = {"mindmap": mindmap_resource}
        save_generated_resource(state, progress=68, stage="思维导图已生成", resource_delta=resource_delta, trace=trace)
        return {"generated_resources": resource_delta, "agent_trace": [trace]}
    except TASK_CONTROL_EXCEPTIONS:
        raise
    except Exception as e:
        trace = add_trace("MindmapGenerator", "failed", f"导图生成失败: {e}", start)
        error_resource = {
            "type": "mindmap",
            "status": "failed",
            "format": "mermaid",
            "title": "思维导图",
            "data": {},
            "error": str(e)
        }
        return {"generated_resources": {"mindmap": error_resource}, "agent_trace": [trace]}
    
def planner_node(state: AgentState) -> AgentState:
    """根据画像和目标制定学习计划表"""
    task_id = state.get("task_id", "")
    ensure_task_can_continue(task_id)

    start = time.time()
    report_progress(state, 70, "Planner 正在规划学习路线")
    logger.info("正在根据画像规划学习路线...", extra={"task_id": state.get("task_id", ""), "agent": "Planner"})
    profile = state.get("student_profile", {})
    prefs = state.get("request_preferences", {})
    effective_profile = {**profile, **prefs}
    
    from src.prompts.generators import PLANNER_PROMPT
    prompt = ChatPromptTemplate.from_template(PLANNER_PROMPT)
    
    fallback_plan = LearningPlanSchema(
        summary="学习计划规划失败，请稍后重试。",
        days=[],
        advice="无"
    )
    
    ensure_task_can_continue(task_id)
    try:
        with task_heartbeat_guard(task_id):
            validated = invoke_structured(
                llm=llm,
                prompt=prompt,
                schema=LearningPlanSchema,
                fallback=fallback_plan,
                task_id=task_id,
                agent_name="Planner",
                input_kwargs={
                    "major": effective_profile.get("major", "未知"),
                    "foundation": effective_profile.get("foundation", "未知"),
                    "cognitive_style": effective_profile.get("cognitive_style", "未知"),
                    "weakness": effective_profile.get("weakness", "未知"),
                    "learning_pace": effective_profile.get("learning_pace", "未知"),
                    "time_budget": effective_profile.get("time_budget", "未知"),
                    "emotional_state": effective_profile.get("emotional_state", "未知"),
                    "preferred_format": effective_profile.get("preferred_format", "未知"),
                    "learning_goal": effective_profile.get("learning_goal", "未知")
                }
            )
        trace = add_trace("Planner", "success", "完成计划生成", start)
        plan_resource = {
            "type": "plan",
            "status": "completed",
            "format": "json",
            "title": "学习路线",
            "data": validated.model_dump()
        }
        resource_delta = {"plan": plan_resource}
        save_generated_resource(state, progress=73, stage="学习计划表已生成", resource_delta=resource_delta, trace=trace)
        return {"generated_resources": resource_delta, "agent_trace": [trace]}
    except TASK_CONTROL_EXCEPTIONS:
        raise
    except Exception as e:
        logger.exception("规划失败", extra={"task_id": state.get("task_id", ""), "agent": "Planner"})
        trace = add_trace("Planner", "failed", f"规划异常: {e}", start)
        error_resource = {
            "type": "plan",
            "status": "failed",
            "format": "json",
            "title": "学习路线",
            "data": {},
            "error": str(e)
        }
        return {
            "generated_resources": {"plan": error_resource}, 
            "agent_trace": [trace]
        }

def tutor_node(state: AgentState) -> AgentState:
    """智能辅导与答疑"""
    task_id = state.get("task_id", "")
    ensure_task_can_continue(task_id)

    start = time.time()
    report_progress(state, 72, "Tutor 正在生成智能答疑")
    logger.info("正在基于 RAG 进行个性化答疑...", extra={"task_id": state.get("task_id", ""), "agent": "Tutor"})

    profile = state.get("student_profile", {})
    prefs = state.get("request_preferences", {})
    effective_profile = {**profile, **prefs}
    context = state.get("retrieved_context", "无参考资料")
    question = state["messages"][-1] if state.get("messages") else ""

    from src.prompts.tutor import TUTOR_PROMPT
    prompt = ChatPromptTemplate.from_template(TUTOR_PROMPT)

    chain = prompt | llm

    ensure_task_can_continue(task_id)
    try:
        with task_heartbeat_guard(task_id):
            res = safe_invoke(chain, {
                "major": effective_profile.get("major", "未知"),
                "foundation": effective_profile.get("foundation", "未知"),
                "cognitive_style": effective_profile.get("cognitive_style", "未知"),
                "learning_goal": effective_profile.get("learning_goal", "未知"),
                "weakness": effective_profile.get("weakness", "未知"),
                "context": context,
                "question": question
            })
        trace = add_trace("Tutor", "success", "完成答疑", start)
        answer_resource = {
            "type": "answer",
            "status": "completed",
            "format": "markdown",
            "title": "智能答疑",
            "data": {"content": res.content}
        }
        resource_delta = {"answer": answer_resource}
        save_generated_resource(state, progress=78, stage="智能答疑已生成", resource_delta=resource_delta, trace=trace)
        return {"generated_resources": resource_delta, "agent_trace": [trace]}
    except TASK_CONTROL_EXCEPTIONS:
        raise
    except Exception as e:
        trace = add_trace("Tutor", "failed", f"答疑生成失败: {e}", start)
        error_resource = {
            "type": "answer",
            "status": "failed",
            "format": "markdown",
            "title": "智能答疑",
            "data": {},
            "error": str(e)
        }
        return {"generated_resources": {"answer": error_resource}, "agent_trace": [trace]}

def reading_generator_node(state: AgentState) -> AgentState:
    """生成拓展阅读材料推荐"""
    task_id = state.get("task_id", "")
    ensure_task_can_continue(task_id)

    start = time.time()
    report_progress(state, 75, "Reading Generator 正在寻找拓展阅读")
    logger.info("正在寻找拓展阅读材料...", extra={"task_id": state.get("task_id", ""), "agent": "ReadingGenerator"})
    retrieved_context = state.get("retrieved_context", "")
    
    from src.prompts.generators import READING_GENERATOR_PROMPT
    prompt = ChatPromptTemplate.from_template(READING_GENERATOR_PROMPT)
    chain = prompt | llm
    
    ensure_task_can_continue(task_id)
    try:
        with task_heartbeat_guard(task_id):
            res = safe_invoke(chain, {"context": retrieved_context})
        trace = add_trace("ReadingGenerator", "success", "完成拓展阅读生成", start)
        reading_resource = {
            "type": "reading",
            "status": "completed",
            "format": "markdown",
            "title": "拓展阅读",
            "data": {"content": res.content}
        }
        resource_delta = {"reading": reading_resource}
        save_generated_resource(state, progress=78, stage="拓展阅读已生成", resource_delta=resource_delta, trace=trace)
        return {"generated_resources": resource_delta, "agent_trace": [trace]}
    except TASK_CONTROL_EXCEPTIONS:
        raise
    except Exception as e:
        trace = add_trace("ReadingGenerator", "failed", f"阅读生成失败: {e}", start)
        error_resource = {
            "type": "reading",
            "status": "failed",
            "format": "markdown",
            "title": "拓展阅读",
            "data": {},
            "error": str(e)
        }
        return {"generated_resources": {"reading": error_resource}, "agent_trace": [trace]}

def code_case_generator_node(state: AgentState) -> AgentState:
    """生成代码类实操案例"""
    task_id = state.get("task_id", "")
    ensure_task_can_continue(task_id)

    start = time.time()
    report_progress(state, 80, "Code Case Generator 正在生成代码案例")
    logger.info("正在生成代码实操案例...", extra={"task_id": state.get("task_id", ""), "agent": "CodeCaseGenerator"})
    retrieved_context = state.get("retrieved_context", "")
    profile = state.get("student_profile", {})
    prefs = state.get("request_preferences", {})
    effective_profile = {**profile, **prefs}
    
    from src.prompts.generators import CODE_CASE_GENERATOR_PROMPT
    prompt = ChatPromptTemplate.from_template(CODE_CASE_GENERATOR_PROMPT)
    chain = prompt | llm
    
    ensure_task_can_continue(task_id)
    try:
        with task_heartbeat_guard(task_id):
            res = safe_invoke(chain, {
                "context": retrieved_context,
                "foundation": effective_profile.get("foundation", "未知")
            })
        trace = add_trace("CodeCaseGenerator", "success", "完成代码案例生成", start)
        code_resource = {
            "type": "code_case",
            "status": "completed",
            "format": "markdown",
            "title": "实操代码",
            "data": {"content": res.content}
        }
        resource_delta = {"code_case": code_resource}
        save_generated_resource(state, progress=83, stage="代码案例已生成", resource_delta=resource_delta, trace=trace)
        return {"generated_resources": resource_delta, "agent_trace": [trace]}
    except TASK_CONTROL_EXCEPTIONS:
        raise
    except Exception as e:
        trace = add_trace("CodeCaseGenerator", "failed", f"代码案例生成失败: {e}", start)
        error_resource = {
            "type": "code_case",
            "status": "failed",
            "format": "markdown",
            "title": "实操代码",
            "data": {},
            "error": str(e)
        }
        return {"generated_resources": {"code_case": error_resource}, "agent_trace": [trace]}

def ppt_generator_node(state: AgentState) -> AgentState:
    """生成演示文稿(PPT)的大纲与幻灯片内容"""
    task_id = state.get("task_id", "")
    ensure_task_can_continue(task_id)

    start = time.time()
    report_progress(state, 85, "PPT Generator 正在生成 PPT 大纲")
    logger.info("正在生成课程演示文稿 PPT 大纲...", extra={"task_id": state.get("task_id", ""), "agent": "PPTGenerator"})
    retrieved_context = state.get("retrieved_context", "")
    profile = state.get("student_profile", {})
    prefs = state.get("request_preferences", {})
    effective_profile = {**profile, **prefs}
    
    from src.prompts.generators import PPT_GENERATOR_PROMPT
    prompt = ChatPromptTemplate.from_template(PPT_GENERATOR_PROMPT)
    chain = prompt | llm
    
    ensure_task_can_continue(task_id)
    try:
        with task_heartbeat_guard(task_id):
            res = safe_invoke(chain, {
                "context": retrieved_context,
                "cognitive_style": effective_profile.get("cognitive_style", "未知")
            })
        trace = add_trace("PPTGenerator", "success", "完成PPT大纲生成", start)
        ppt_resource = {
            "type": "ppt",
            "status": "completed",
            "format": "markdown",
            "title": "演示文稿",
            "data": {"content": res.content}
        }
        resource_delta = {"ppt": ppt_resource}
        save_generated_resource(state, progress=88, stage="PPT大纲已生成", resource_delta=resource_delta, trace=trace)
        return {"generated_resources": resource_delta, "agent_trace": [trace]}
    except TASK_CONTROL_EXCEPTIONS:
        raise
    except Exception as e:
        trace = add_trace("PPTGenerator", "failed", f"PPT生成失败: {e}", start)
        error_resource = {
            "type": "ppt",
            "status": "failed",
            "format": "markdown",
            "title": "演示文稿",
            "data": {},
            "error": str(e)
        }
        return {"generated_resources": {"ppt": error_resource}, "agent_trace": [trace]}

from src.schema.models import LearningEvaluation

def evaluator_node(state: AgentState) -> AgentState:
    """动态评估用户的答题情况，生成错题分析"""
    task_id = state.get("task_id", "")
    ensure_task_can_continue(task_id)
    start = time.time()
    report_progress(state, 50, "正在评估学习效果并进行错题分析")
    
    last_message = state["messages"][-1] if state["messages"] else ""
    context = state.get("retrieved_context", "")
    
    prompt = ChatPromptTemplate.from_template('''
    你是资深的课程导师，请根据用户提交的测验答案以及相关知识，对用户的掌握情况进行评估。
    
    [相关知识]
    {context}
    
    [用户作答]
    {last_message}
    
    请严格输出符合格式的评估报告，包括掌握程度、薄弱知识点列表、针对薄弱点的学习建议以及量化评分(0-100)。
    ''')
    
    ensure_task_can_continue(task_id)
    try:
        with task_heartbeat_guard(task_id):
            validated = invoke_structured(
                llm=llm,
                prompt=prompt,
                schema=LearningEvaluation,
                fallback=LearningEvaluation(mastery_level="未知", weak_points=[], remedial_suggestion="无法准确评估", score=0),
                task_id=task_id,
                agent_name="Evaluator",
                input_kwargs={"context": context, "last_message": last_message},
                strategy="parser"
            )
        
        trace = add_trace("Evaluator", "success", "完成答题评估", start)
        eval_resource = {
            "type": "evaluation",
            "status": "completed",
            "format": "json",
            "title": "错题分析报告",
            "data": validated.model_dump()
        }
        save_generated_resource(state, progress=70, stage="错题分析已生成", resource_delta={"evaluation": eval_resource}, trace=trace)
        return {"generated_resources": {"evaluation": eval_resource}, "agent_trace": [trace]}
    except TASK_CONTROL_EXCEPTIONS:
        raise
    except Exception as e:
        trace = add_trace("Evaluator", "failed", f"评估异常: {e}", start)
        error_resource = {
            "type": "evaluation",
            "status": "failed",
            "format": "json",
            "title": "错题分析报告",
            "data": {},
            "error": str(e)
        }
        return {"generated_resources": {"evaluation": error_resource}, "agent_trace": [trace]}

def remedial_tutor_node(state: AgentState) -> AgentState:
    """根据薄弱点生成补充讲解和变式练习"""
    task_id = state.get("task_id", "")
    ensure_task_can_continue(task_id)
    start = time.time()
    report_progress(state, 80, "正在针对薄弱点生成补充讲解和变式练习")
    
    eval_res = state.get("generated_resources", {}).get("evaluation", {})
    if not isinstance(eval_res, dict) or eval_res.get("status") != "completed":
        trace = add_trace("RemedialTutor", "warning", "没有有效的评估数据", start)
        return {"agent_trace": [trace]}
        
    weak_points = eval_res.get("data", {}).get("weak_points", [])
    
    if not weak_points:
        trace = add_trace("RemedialTutor", "success", "无需补充讲解", start)
        return {"agent_trace": [trace]}
        
    prompt = ChatPromptTemplate.from_template('''
    你是资深课程导师。学生在刚刚的测验中暴露了以下薄弱点：
    {weak_points}
    
    请针对这些薄弱点，提供一次简短的“补充讲解”以及 1 道“变式练习题”供学生巩固。
    要求：
    1. 讲解需要通俗易懂，直击痛点。
    2. 变式练习必须带答案解析。
    请使用 Markdown 格式输出。
    ''')
    
    chain = prompt | llm
    
    ensure_task_can_continue(task_id)
    try:
        with task_heartbeat_guard(task_id):
            res = safe_invoke(chain, {"weak_points": ", ".join(weak_points)})
        trace = add_trace("RemedialTutor", "success", "完成查漏补缺", start)
        remedial_resource = {
            "type": "remedial",
            "status": "completed",
            "format": "markdown",
            "title": "查漏补缺",
            "data": {"content": res.content}
        }
        save_generated_resource(state, progress=90, stage="补充讲解与变式练习已生成", resource_delta={"remedial": remedial_resource}, trace=trace)
        return {"generated_resources": {"remedial": remedial_resource}, "agent_trace": [trace]}
    except TASK_CONTROL_EXCEPTIONS:
        raise
    except Exception as e:
        trace = add_trace("RemedialTutor", "failed", f"补充讲解生成失败: {e}", start)
        error_resource = {
            "type": "remedial",
            "status": "failed",
            "format": "markdown",
            "title": "查漏补缺",
            "data": {},
            "error": str(e)
        }
        return {"generated_resources": {"remedial": error_resource}, "agent_trace": [trace]}
