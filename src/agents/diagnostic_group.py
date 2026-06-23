from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from src.schema.state import AgentState
from src.schema.models import StudentProfileSchema
import os
import time
from src.utils.trace import add_trace
from src.utils.progress import report_progress

from src.config.settings import settings

# 初始化大模型
llm = ChatOpenAI(
    model=settings.llm_model_name, 
    temperature=0.3,
    request_timeout=settings.model_request_timeout,
    max_retries=settings.model_max_retries,
)

profile_llm = ChatOpenAI(
    model=settings.llm_model_name,
    temperature=0.1,
    request_timeout=settings.profile_request_timeout,
    max_retries=0,
)
from src.utils.logger import get_logger
from src.utils.structured_output import invoke_structured
from src.schemas.profile import StudentProfileSchema

from src.utils.llm_semaphore import safe_invoke

logger = get_logger("diagnostic_group")

def check_cancellation_and_deadline(state: AgentState, agent_name: str) -> None:
    from src.runtime.task_store import ensure_task_active
    ensure_task_active(state)

def save_diagnostic_progress(state: AgentState, progress: int, stage: str, **payload) -> None:
    from src.runtime.task_store import ensure_task_can_continue, TaskStateConflictError
    task_id = state.get("task_id")
    
    saved = report_progress(state, progress, stage, **payload)
    if saved:
        return
        
    if task_id:
        ensure_task_can_continue(task_id)
        
    raise TaskStateConflictError(f"任务 {task_id} 的状态已发生变化，禁止继续写入")

def extract_local_profile_delta(text: str) -> tuple[dict, dict]:
    profile_delta = {}
    pref_delta = {}
    
    if any(k in text for k in ["专业一点", "严谨一点", "学术一点", "专业性强"]):
        pref_delta["preferred_format"] = "严谨学术"
    elif any(k in text for k in ["简单一点", "通俗一点", "白话一点"]):
        pref_delta["preferred_format"] = "通俗白话"

    if any(k in text for k in ["图解", "图示", "可视化"]):
        pref_delta["cognitive_style"] = "图文驱动"
    elif any(k in text for k in ["代码案例", "代码实战", "动手实践"]):
        pref_delta["cognitive_style"] = "代码实战"
    elif any(k in text for k in ["公式推导", "数学推导"]):
        pref_delta["cognitive_style"] = "公式推导"

    if any(k in text for k in ["详细了解", "深入学习", "深入理解", "系统学习"]):
        pref_delta["learning_pace"] = "深度探究"
    elif any(k in text for k in ["快速掌握", "速成", "尽快学会"]):
        pref_delta["learning_pace"] = "速成突破"

    return profile_delta, pref_delta

PROFILE_SIGNAL_KEYWORDS = [
    "我是", "我的专业", "基础", "不理解", "不擅长", "薄弱", 
    "学习目标", "希望在", "每天", "一周", "一个月", "焦虑", 
    "迷茫", "偏好", "喜欢"
]

def requires_profile_llm(text: str) -> bool:
    return any(keyword in text for keyword in PROFILE_SIGNAL_KEYWORDS)

def extract_profile_with_llm(task_id: str, current_profile: dict, last_message: str, start: float) -> dict:
    from src.prompts.profiler import PROFILE_SYSTEM_PROMPT
    from src.schemas.profile import StudentProfileDeltaSchema
    from src.runtime.task_store import task_heartbeat_guard, ensure_task_can_continue, TaskCancelledError, TaskExpiredError, TaskAlreadyFinishedError, TaskStateConflictError
    TASK_CONTROL_EXCEPTIONS = (TaskCancelledError, TaskExpiredError, TaskAlreadyFinishedError, TaskStateConflictError)
    
    prompt = ChatPromptTemplate.from_template(PROFILE_SYSTEM_PROMPT)
    fallback_profile = StudentProfileDeltaSchema()
    
    try:
        import json
        current_profile_str = json.dumps(current_profile, ensure_ascii=False)
        
        if task_id:
            with task_heartbeat_guard(task_id):
                validated = invoke_structured(
                    llm=profile_llm,
                    prompt=prompt,
                    schema=StudentProfileDeltaSchema,
                    fallback=fallback_profile,
                    task_id=task_id,
                    agent_name="Profiler",
                    input_kwargs={"input": last_message, "current_profile": current_profile_str},
                    strategy="parser",
                    allow_retry=False
                )
            ensure_task_can_continue(task_id)
        else:
            validated = invoke_structured(
                llm=profile_llm,
                prompt=prompt,
                schema=StudentProfileDeltaSchema,
                fallback=fallback_profile,
                task_id=task_id,
                agent_name="Profiler",
                input_kwargs={"input": last_message, "current_profile": current_profile_str},
                strategy="parser",
                allow_retry=False
            )
        
        delta = validated.model_dump(exclude_none=True)
        final_profile = dict(current_profile)
        
        for k, v in delta.items():
            if v and v not in ["未知", "未识别", "未明确", "未说明"]:
                final_profile[k] = v

        logger.info(f"成功提取并更新画像: {final_profile}", extra={"task_id": task_id, "agent": "Profiler"})
        trace = add_trace("Profiler", "success", "完成学生画像提取", start)
        return {"student_profile": final_profile, "agent_trace": [trace]}
        
    except TASK_CONTROL_EXCEPTIONS:
        raise
    except Exception as exc:
        logger.warning(
            f"画像更新失败，复用已有画像：{exc}",
            extra={"task_id": task_id, "agent": "Profiler"}
        )
        trace = add_trace("Profiler", "warning", "画像更新超时，已复用历史画像", start)
        return {"student_profile": current_profile, "agent_trace": [trace]}

def profiler_node(state: AgentState) -> dict:
    """提取学生特征并动态更新画像 (调用大模型结构化输出)"""
    check_cancellation_and_deadline(state, "Profiler")

    start = time.time()
    messages = state.get("messages", [])
    last_message = messages[-1] if messages else ""
    
    current_profile = dict(state.get("student_profile") or {})
    request_preferences = dict(state.get("request_preferences") or {})
    
    save_diagnostic_progress(state, 15, "Profiler 正在检查学生画像")
    
    logger.info(f"正在深度分析输入: '{last_message}'", extra={"task_id": state.get("task_id", ""), "agent": "Profiler"})
    
    # 快速路径一：本地规则可以直接识别变化
    local_profile_delta, local_pref_delta = extract_local_profile_delta(last_message)
    
    if local_profile_delta or local_pref_delta:
        current_profile.update(local_profile_delta)
        request_preferences.update(local_pref_delta)
        
        trace = add_trace("Profiler", "success", "本地更新临时偏好或画像", start)
        save_diagnostic_progress(state, 25, "学生画像已快速更新", student_profile=current_profile, agent_trace=[trace])
        return {"student_profile": current_profile, "request_preferences": request_preferences, "profile_dirty": False, "agent_trace": [trace]}
        
    # 快速路径二：已有画像，并且本轮没有提供新画像信息
    if current_profile and not requires_profile_llm(last_message):
        trace = add_trace("Profiler", "success", "画像无实质变化，启用缓存复用策略", start)
        save_diagnostic_progress(state, 25, "已复用现有学生画像", student_profile=current_profile, agent_trace=[trace])
        return {"student_profile": current_profile, "request_preferences": request_preferences, "profile_dirty": False, "agent_trace": [trace]}
        
    # 慢速路径：首次画像或复杂画像变化才调用模型
    result = extract_profile_with_llm(
        task_id=state.get("task_id", ""),
        current_profile=current_profile,
        last_message=last_message,
        start=start
    )
    if "student_profile" in result:
        save_diagnostic_progress(state, 25, "学生画像已生成", student_profile=result["student_profile"])
    result["request_preferences"] = request_preferences
    result["profile_dirty"] = True
    return result

from src.rag.vector_store import retrieve_authorized_documents

def diagnoser_node(state: AgentState) -> dict:
    """负责检索知识库，寻找最相关的参考内容。"""
    check_cancellation_and_deadline(state, "Diagnoser")

    start = time.time()
    save_diagnostic_progress(state, 30, "Diagnoser 正在检索课程知识库")
    logger.info("正在提取关键学习需求并执行检索...", extra={"task_id": state.get("task_id", ""), "agent": "Diagnoser"})
    last_message = state["messages"][-1] if state["messages"] else ""
    
    try:
        from src.runtime.task_store import TaskCancelledError, TaskExpiredError, TaskAlreadyFinishedError, TaskStateConflictError
        TASK_CONTROL_EXCEPTIONS = (TaskCancelledError, TaskExpiredError, TaskAlreadyFinishedError, TaskStateConflictError)
        mode = state.get("mode", "快速模式")
        k = 3 if mode == "快速模式" else 5
        try:
            # 采用全新的受限三段式查询
            task_id = state.get("task_id", "")
            if task_id:
                from src.runtime.task_store import task_heartbeat_guard, ensure_task_can_continue
                with task_heartbeat_guard(task_id):
                    docs = retrieve_authorized_documents(
                        query=last_message,
                        user_id=state.get("user_id"),
                        course_id=state.get("course_id"),
                        conversation_id=state.get("conversation_id"),
                        final_k=k
                    )
                ensure_task_can_continue(task_id)
            else:
                docs = retrieve_authorized_documents(
                    query=last_message,
                    user_id=state.get("user_id"),
                    course_id=state.get("course_id"),
                    conversation_id=state.get("conversation_id"),
                    final_k=k
                )
        except RuntimeError as e:
            trace = add_trace("Diagnoser", "failed", str(e), start)
            save_diagnostic_progress(state, 40, "知识库检索失败", agent_trace=[trace])
            return {"retrieved_context": "", "retrieved_sources": [], "agent_trace": [trace]}
        
        if docs:
            sources = []
            context_blocks = []
            
            for idx, d in enumerate(docs):
                source = d.metadata.get("source", "未知来源")
                page = d.metadata.get("page", "未知页码")
                chunk_id = d.metadata.get("chunk_id", f"chunk_{idx + 1}")
                
                context_blocks.append(
                    f"[{chunk_id}] 来源：{source}，页码：{page}\n{d.page_content}"
                )
                
                sources.append({
                    "chunk_id": chunk_id,
                    "source": source,
                    "page": page,
                    "preview": d.page_content[:120]
                })
            
            logger.info(f"成功从知识库检索到 {len(docs)} 个相关知识块！", extra={"task_id": state.get("task_id", ""), "agent": "Diagnoser"})
            trace = add_trace("Diagnoser", "success", f"检索到 {len(docs)} 个知识块", start)
            save_diagnostic_progress(
                state,
                40,
                "课程知识库检索完成",
                retrieved_sources=sources,
                agent_trace=[trace]
            )
            return {"retrieved_context": "\n\n---\n\n".join(context_blocks), "retrieved_sources": sources, "agent_trace": [trace]}
        else:
            logger.info("知识库中未找到高度相关内容。", extra={"task_id": state.get("task_id", ""), "agent": "Diagnoser"})
            trace = add_trace("Diagnoser", "success", "未检索到相关教材内容", start)
            save_diagnostic_progress(
                state,
                40,
                "知识库暂不可用",
                agent_trace=[trace]
            )
            return {"retrieved_context": "未检索到相关教材内容。", "retrieved_sources": [], "agent_trace": [trace]}
            
    except TASK_CONTROL_EXCEPTIONS:
        raise
    except Exception as e:
        logger.exception("检索系统异常", extra={"task_id": state.get("task_id", ""), "agent": "Diagnoser"})
        trace = add_trace("Diagnoser", "failed", f"检索异常: {e}", start)
        
        task_id = state.get("task_id")
        if task_id:
            from src.runtime.task_store import ensure_task_can_continue
            ensure_task_can_continue(task_id)
            
        save_diagnostic_progress(
            state,
            40,
            "知识库检索失败",
            agent_trace=[trace]
        )
        return {"retrieved_context": "检索服务异常。", "retrieved_sources": [], "agent_trace": [trace]}

def router_node(state: AgentState) -> str:
    """系统大门路由器，判断意图，决定子图流转方向 (纯规则引擎)"""
    start = time.time()
    mode = state.get("mode", "")
    last_message = state["messages"][-1] if state.get("messages") else ""

    ask_keywords = ["为什么", "怎么理解", "是什么", "解释", "区别", "不会", "报错"]
    practice_keywords = ["做题", "练习", "测验", "考试", "刷题"]
    evaluate_keywords = ["选", "我的答案", "答案是", "我选", "提交"]

    if any(k in last_message for k in evaluate_keywords):
        intent = "want_to_evaluate"
    elif any(k in last_message for k in practice_keywords):
        intent = "want_to_practice"
    elif any(k in last_message for k in ask_keywords):
        intent = "want_to_ask"
    elif mode == "答疑模式":
        intent = "want_to_ask"
    else:
        intent = "want_to_learn"

    logger.info(f"识别到意图并流转至子模块: {intent}", extra={"task_id": state.get("task_id", ""), "agent": "Router"})
    return intent
