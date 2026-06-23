from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
import os
import threading
import logging

from src.graph.workflow import build_graph
from src.runtime.task_store import (
    create_task, update_task, get_task, find_running_task_by_user,
    find_task_by_request_id, TaskCancelledError, TaskExpiredError,
    TaskAlreadyFinishedError, TaskStateConflictError, ensure_task_can_continue,
    request_task_cancel, complete_task, finish_cancelled_task, fail_task,
    recover_tasks_on_startup, recover_stale_tasks, update_task_progress,
    finalize_active_task_metadata, expire_task
)
from src.runtime.task_status import is_terminal_status
from fastapi.responses import StreamingResponse
import asyncio
import json

from src.api.knowledge import router as knowledge_router

logger = logging.getLogger(__name__)

app = FastAPI(title="EduAgentX API")
app.include_router(knowledge_router)

@app.on_event("startup")
def on_startup():
    recovered = recover_tasks_on_startup()
    logger.info("Recovered %s interrupted tasks on startup", recovered)
    
    try:
        from src.knowledge.service import recover_indexing_tasks_on_startup, submit_index_task, cleanup_failed_index_vectors
        recovered_idx_tasks = recover_indexing_tasks_on_startup()
        logger.info("Recovered %s interrupted indexing tasks on startup", len(recovered_idx_tasks))
        for task in recovered_idx_tasks:
            submit_index_task(task["index_task_id"], task["document_id"])
            
        import threading
        threading.Thread(target=cleanup_failed_index_vectors, daemon=True).start()
    except Exception as e:
        logger.error("Failed to recover indexing tasks: %s", e)

    def heartbeat_checker():
        import time
        while True:
            try:
                time.sleep(60)
                result = recover_stale_tasks(300)
                if result["total"] > 0:
                    logger.info("Recovered stale tasks: cancelled=%s, expired=%s", result["cancelled"], result["expired"])
            except Exception as e:
                logger.error("Heartbeat checker error: %s", e)

    t = threading.Thread(target=heartbeat_checker, daemon=True)
    t.start()

def serialize_task(task: dict) -> dict:
    result = dict(task)
    result["is_terminal"] = is_terminal_status(task.get("status"))
    return result

# Initialize the multi-agent graph once when server starts
workflow = build_graph()

class ChatRequest(BaseModel):
    user_input: str
    history: List[Dict[str, Any]] = []

class AsyncChatRequest(BaseModel):
    user_input: str
    mode: str = "快速模式"
    requested_resources: List[str] = []
    interaction_level: str = "standard"
    user_id: str = "demo_user"
    conversation_id: str = ""
    course_id: Optional[str] = None
    request_id: str = ""
    student_profile: Dict[str, Any] = {}
    history: List[Dict[str, Any]] = []

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    messages = [h["content"] for h in request.history] + [request.user_input]
    
    # Prepare the initial state
    initial_state = {
        "messages": messages,
        "student_profile": {},
        "generated_resources": {},
        "retrieved_context": "",
        "retrieved_sources": [],
        "agent_trace": [],
        "task_id": "",
        "mode": "同步模式",
        "user_id": "demo_user"
    }
    
    # Execute the LangGraph workflow
    max_concurrency = int(os.getenv("AGENT_MAX_CONCURRENCY", "3"))
    final_state = workflow.invoke(
        initial_state,
        config={"recursion_limit": 50, "max_concurrency": max_concurrency}
    )
    
    return {
        "student_profile": final_state.get("student_profile", {}),
        "generated_resources": final_state.get("generated_resources", {}),
        "review_feedback": final_state.get("review_feedback", ""),
        "retrieved_sources": final_state.get("retrieved_sources", []),
        "agent_trace": final_state.get("agent_trace", [])
    }

@app.post("/api/chat/async")
def chat_async(request: AsyncChatRequest):
    if request.request_id:
        existing_task_id = find_task_by_request_id(request.request_id)
        if existing_task_id:
            return {
                "task_id": existing_task_id,
                "status": "running",
                "message": "任务已存在，无需重复提交。"
            }

    running_task = find_running_task_by_user(request.user_id)
    if running_task:
        raise HTTPException(
            status_code=409,
            detail="当前已有任务正在执行，请等待任务结束后再提交。"
        )

    task_id = create_task(
        request.user_input, 
        request.user_id, 
        request.conversation_id, 
        "", 
        request.request_id,
        request.requested_resources
    )

    thread = threading.Thread(
        target=run_agent_task,
        args=(task_id, request),
        daemon=True
    )
    thread.start()

    return {
        "task_id": task_id,
        "status": "running",
        "message": "任务已创建，正在由多智能体协同生成资源。"
    }

@app.post("/api/task/{task_id}/cancel")
def cancel_task_endpoint(task_id: str):
    latest = request_task_cancel(task_id)
    if latest is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if is_terminal_status(latest.get("status")):
        return serialize_task(latest)
    
    return {
        **serialize_task(latest),
        "message": "已提交取消请求，当前执行节点结束后将停止任务。"
    }

@app.get("/api/task/{task_id}")
def get_task_status(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return serialize_task(task)

@app.get("/api/task/{task_id}/stream")
async def stream_task_status(task_id: str):
    async def event_generator():
        last_updated_at = 0
        import time
        last_yield_time = time.time()
        
        while True:
            task = get_task(task_id)
            if not task:
                yield f"data: {json.dumps({'error': '任务不存在'})}\n\n"
                break
                
            current_updated_at = task.get("updated_at", 0)
            was_yielded = False
            if current_updated_at > last_updated_at:
                last_updated_at = current_updated_at
                yield f"data: {json.dumps(serialize_task(task))}\n\n"
                last_yield_time = time.time()
                was_yielded = True
            else:
                # SSE keep-alive ping every 15 seconds
                if time.time() - last_yield_time > 15:
                    yield ": keep-alive\n\n"
                    last_yield_time = time.time()
                
            if is_terminal_status(task.get("status")):
                # Ensure we push the terminal state if not pushed yet
                if not was_yielded:
                    yield f"data: {json.dumps(serialize_task(task))}\n\n"
                break
                
            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

def run_agent_task(task_id: str, request: AsyncChatRequest):
    try:
        from src.runtime.task_store import get_last_conversation_summary
        conversation_summary = get_last_conversation_summary(request.conversation_id) if request.conversation_id else ""

        update_task_progress(
            task_id,
            progress=5,
            current_stage="初始化多智能体工作流"
        )

        messages = [h.get("content", "") for h in request.history] + [request.user_input]
        if conversation_summary:
            messages.insert(0, f"【之前的对话摘要】\n{conversation_summary}")
        
        import time
        task_deadline = time.time() + (300 if request.mode == "完整模式" else 120)

        initial_state = {
            "messages": messages,
            "student_profile": request.student_profile,
            "request_preferences": {},
            "current_intent": "",
            "generated_resources": {},
            "retrieved_context": "",
            "retrieved_sources": [],
            "pending_tasks": [],
            "requested_resources": request.requested_resources,
            "review_feedback": "",
            "agent_trace": [],
            "task_id": task_id,
            "task_deadline": task_deadline,
            "mode": request.mode,
            "user_id": request.user_id,
            "conversation_id": request.conversation_id,
            "course_id": request.course_id
        }

        max_concurrency = int(os.getenv("AGENT_MAX_CONCURRENCY", "3"))
        
        final_state = workflow.invoke(
            initial_state,
            config={"recursion_limit": 50, "max_concurrency": max_concurrency}
        )

        def build_task_title(text: str, max_length: int = 18) -> str:
            import re
            normalized = re.sub(r"\s+", " ", text).strip()

            for prefix in [
                "我是计算机专业大二学生，",
                "我想学习",
                "请帮我",
                "请给我",
                "帮我",
            ]:
                if normalized.startswith(prefix):
                    normalized = normalized[len(prefix):].strip()

            if not normalized:
                return "新学习任务"

            if len(normalized) <= max_length:
                return normalized

            return normalized[:max_length] + "..."
        
        task_title = build_task_title(request.user_input)

        ensure_task_can_continue(task_id)

        saved = finalize_active_task_metadata(
            task_id,
            task_title=task_title,
            student_profile=final_state.get("student_profile", {}),
            retrieved_sources=final_state.get("retrieved_sources", []),
            agent_trace=final_state.get("agent_trace", []),
            review_feedback=final_state.get("review_feedback", ""),
            conversation_summary=conversation_summary,
            replace_agent_trace=True
        )

        if not saved:
            latest = get_task(task_id)
            if latest and latest.get("status") == "cancel_requested":
                finish_cancelled_task(task_id)
            return

        if not complete_task(
            task_id,
            resources=final_state.get("generated_resources", {})
        ):
            latest = get_task(task_id)
            if latest and latest.get("status") == "cancel_requested":
                finish_cancelled_task(task_id)
                return
            elif latest and is_terminal_status(latest.get("status")):
                return
            else:
                raise TaskStateConflictError(f"Task {task_id} failed to complete")

        if request.conversation_id:
            def generate_summary():
                try:
                    from src.agents.diagnostic_group import profile_llm as summary_llm
                    from langchain_core.prompts import ChatPromptTemplate
                    prompt = ChatPromptTemplate.from_template("请总结以下对话的上下文和学生的当前学习状态，尽量简短(100字以内)。之前的摘要:\n{summary}\n\n最新对话:\n{messages}")
                    chain = prompt | summary_llm
                    from src.utils.llm_semaphore import safe_invoke
                    res = safe_invoke(chain, {"summary": conversation_summary, "messages": messages})
                    update_task(task_id, conversation_summary=res.content)
                except Exception:
                    pass
            
            import threading
            threading.Thread(target=generate_summary, daemon=True).start()

    except TaskCancelledError:
        finish_cancelled_task(task_id)
    except TaskAlreadyFinishedError:
        logger.info("Task %s was already in terminal state", task_id)
    except TaskExpiredError as exc:
        latest = get_task(task_id)
        if latest is None:
            logger.warning("Expired task no longer exists: %s", task_id)
        elif latest["status"] == "cancel_requested":
            finish_cancelled_task(task_id)
        elif is_terminal_status(latest["status"]):
            logger.info("Task %s already finished as %s", task_id, latest["status"])
        else:
            expire_task(task_id, reason=str(exc) or "任务执行超时")
    except TaskStateConflictError as exc:
        latest = get_task(task_id)
        if latest and latest.get("status") == "cancel_requested":
            finish_cancelled_task(task_id)
        elif latest and is_terminal_status(latest.get("status")):
            return
        else:
            fail_task(task_id, stage="任务状态发生冲突", error=str(exc))
    except Exception as exc:
        logger.exception("Agent task failed")
        latest = get_task(task_id)
        if latest and latest.get("status") == "cancel_requested":
            finish_cancelled_task(task_id)
        elif latest and is_terminal_status(latest.get("status")):
            return
        else:
            fail_task(task_id, stage="任务执行失败", error=str(exc))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
