import uuid
import time
import json
from typing import Dict, Any
from src.db.database import get_connection
from src.runtime.task_status import is_terminal_status, is_active_status
from contextlib import contextmanager
from threading import Event, Thread

class TaskCancelledError(Exception):
    pass

class TaskExpiredError(Exception):
    pass

class TaskAlreadyFinishedError(Exception):
    pass

class TaskNotFoundError(Exception):
    pass

class TaskStateConflictError(RuntimeError):
    pass

def ensure_task_can_continue(task_id: str) -> None:
    task = get_task(task_id)

    if task is None:
        raise TaskNotFoundError(task_id)

    if task["status"] == "cancel_requested":
        raise TaskCancelledError(task_id)

    if is_terminal_status(task["status"]):
        raise TaskAlreadyFinishedError(task_id)

def ensure_task_active(state: dict):
    task_id = state.get("task_id")
    if task_id:
        ensure_task_can_continue(task_id)
    task_deadline = state.get("task_deadline")
    if task_deadline and time.time() > task_deadline:
        raise TaskExpiredError("任务执行超时")

def create_task(user_input: str = "", user_id: str = "", conversation_id: str = "", conversation_summary: str = "", request_id: str = "", requested_resources: list = None) -> str:
    if requested_resources is None:
        requested_resources = []
    task_id = str(uuid.uuid4())
    now = time.time()
    
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO tasks (
            task_id, user_input, status, progress, current_stage, task_title,
            student_profile, generated_resources, retrieved_sources, agent_trace,
            review_feedback, error, created_at, updated_at, user_id, conversation_id, conversation_summary, request_id,
            started_at, heartbeat_at, requested_resources, retry_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        task_id, user_input, "pending", 0, "任务已创建", "",
        "{}", "{}", "[]", "[]", "", None, now, now, user_id, conversation_id, conversation_summary, request_id,
        now, now, json.dumps(requested_resources, ensure_ascii=False), 0
    ))
    conn.commit()
    conn.close()
    return task_id

def find_task_by_request_id(request_id: str) -> str:
    if not request_id:
        return None
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT task_id FROM tasks WHERE request_id = ?", (request_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return row['task_id']
    return None

def is_task_cancelled(task_id: str) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT status FROM tasks WHERE task_id = ?", (task_id,))
    row = c.fetchone()
    conn.close()
    if row and row['status'] == 'cancelled':
        return True
    return False

def is_cancel_requested(task_id: str) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT status FROM tasks WHERE task_id = ?", (task_id,))
    row = c.fetchone()
    conn.close()
    if row and row['status'] in ('cancel_requested', 'cancelled'):
        return True
    return False

def request_task_cancel(task_id: str) -> Dict[str, Any]:
    now = time.time()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE tasks
            SET status = 'cancel_requested',
                cancel_requested_at = ?,
                current_stage = '已收到取消请求，正在停止任务',
                heartbeat_at = ?,
                updated_at = ?
            WHERE task_id = ?
              AND status IN ('pending', 'running')
            """,
            (now, now, now, task_id),
        )
        conn.commit()

    return get_task(task_id)

def cancel_task(task_id: str):
    request_task_cancel(task_id)

def get_last_conversation_summary(conversation_id: str) -> str:
    if not conversation_id:
        return ""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT conversation_summary FROM tasks WHERE conversation_id = ? ORDER BY created_at DESC LIMIT 1", (conversation_id,))
    row = c.fetchone()
    conn.close()
    if row and row['conversation_summary']:
        return row['conversation_summary']
    return ""

def recover_tasks_on_startup() -> dict[str, int]:
    now = time.time()
    with get_connection() as conn:
        cancelled_cursor = conn.execute(
            """
            UPDATE tasks
            SET status = 'cancelled',
                current_stage = '任务已取消',
                completed_at = ?,
                updated_at = ?
            WHERE status = 'cancel_requested'
            """,
            (now, now),
        )

        interrupted_cursor = conn.execute(
            """
            UPDATE tasks
            SET status = 'interrupted',
                current_stage = '任务因服务中断而停止，可重新执行',
                completed_at = ?,
                updated_at = ?
            WHERE status IN ('pending', 'running')
            """,
            (now, now),
        )

        conn.commit()

    return {
        "cancelled": cancelled_cursor.rowcount,
        "interrupted": interrupted_cursor.rowcount,
    }

def recover_stale_tasks(timeout_seconds: int = 300, user_id: str = None) -> dict[str, int]:
    now = time.time()
    deadline = now - timeout_seconds
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        
        user_cond = "AND user_id = ?" if user_id else ""
        params_cancelled = (now, now, deadline, user_id) if user_id else (now, now, deadline)
        
        cancelled_cursor = conn.execute(
            f"""
            UPDATE tasks
            SET status = 'cancelled',
                current_stage = '任务已取消',
                completed_at = ?,
                updated_at = ?
            WHERE status = 'cancel_requested'
              AND (
                  heartbeat_at IS NULL
                  OR heartbeat_at < ?
              )
              {user_cond}
            """,
            params_cancelled,
        )
        
        expired_cursor = conn.execute(
            f"""
            UPDATE tasks
            SET status = 'expired',
                current_stage = '任务心跳超时，可重新执行',
                error = '任务心跳超时',
                completed_at = ?,
                updated_at = ?
            WHERE status IN ('pending', 'running')
              AND (
                  heartbeat_at IS NULL
                  OR heartbeat_at < ?
              )
              {user_cond}
            """,
            params_cancelled,
        )
        
        conn.commit()
        
    cancelled_count = cancelled_cursor.rowcount
    expired_count = expired_cursor.rowcount
    return {
        "cancelled": cancelled_count,
        "expired": expired_count,
        "total": cancelled_count + expired_count
    }

def find_running_task_by_user(user_id: str) -> Dict[str, Any]:
    if not user_id:
        return None
    recover_stale_tasks(timeout_seconds=300, user_id=user_id)
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM tasks WHERE user_id = ? AND status IN ('pending', 'running', 'cancel_requested') ORDER BY created_at DESC LIMIT 1", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def update_task(
    task_id: str,
    *,
    replace_generated_resources: bool = False,
    replace_agent_trace: bool = False,
    **kwargs
):
    forbidden_fields = {"status", "completed_at", "cancel_requested_at"}
    invalid = forbidden_fields.intersection(kwargs.keys())
    if invalid:
        raise ValueError(f"状态字段必须通过专用转换函数修改：{invalid}")

    max_retries = 3
    for attempt in range(max_retries):
        try:
            conn = get_connection()
            c = conn.cursor()
            
            c.execute("BEGIN IMMEDIATE")
            
            c.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
            row = c.fetchone()
            if not row:
                conn.rollback()
                conn.close()
                return

            task = dict(row)
            now = time.time()
            updates = {"updated_at": now}

            if "progress" in kwargs:
                old_progress = task.get("progress", 0)
                new_progress = kwargs["progress"]
                updates["progress"] = max(old_progress, new_progress)
                kwargs.pop("progress")

            if "generated_resources" in kwargs:
                incoming = kwargs.pop("generated_resources")
                if replace_generated_resources:
                    updates["generated_resources"] = json.dumps(incoming, ensure_ascii=False)
                else:
                    existing = json.loads(task["generated_resources"]) if task["generated_resources"] else {}
                    existing.update(incoming)
                    updates["generated_resources"] = json.dumps(existing, ensure_ascii=False)

            if "agent_trace" in kwargs:
                incoming = kwargs.pop("agent_trace")
                if replace_agent_trace:
                    updates["agent_trace"] = json.dumps(incoming, ensure_ascii=False)
                else:
                    existing = json.loads(task["agent_trace"]) if task["agent_trace"] else []
                    existing.extend(incoming)
                    updates["agent_trace"] = json.dumps(existing, ensure_ascii=False)

            for k, v in kwargs.items():
                if isinstance(v, (dict, list)):
                    updates[k] = json.dumps(v, ensure_ascii=False)
                else:
                    updates[k] = v

            set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
            values = list(updates.values()) + [task_id]

            c.execute(f"UPDATE tasks SET {set_clause} WHERE task_id = ?", values)
            conn.commit()
            conn.close()
            break
        except Exception as e:
            try:
                conn.rollback()
            except:
                pass
            if 'database is locked' in str(e) and attempt < max_retries - 1:
                time.sleep(1)
                continue
            raise

def get_task(task_id: str) -> Dict[str, Any]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
    row = c.fetchone()
    conn.close()
    
    if not row:
        return None
        
    task = dict(row)
    
    # Parse JSON fields
    for field in ["student_profile", "generated_resources", "retrieved_sources", "agent_trace"]:
        if task.get(field):
            try:
                task[field] = json.loads(task[field])
            except:
                task[field] = {} if field in ["student_profile", "generated_resources"] else []
                
    return task

def update_task_progress(task_id: str, *, progress: int, current_stage: str) -> bool:
    now = time.time()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE tasks
            SET progress = ?,
                current_stage = ?,
                heartbeat_at = ?,
                updated_at = ?
            WHERE task_id = ?
              AND status IN ('pending', 'running')
            """,
            (progress, current_stage, now, now, task_id),
        )
        rowcount = cursor.rowcount
        conn.commit()
        return rowcount == 1

def update_active_task(
    task_id: str,
    *,
    progress: int | None = None,
    current_stage: str | None = None,
    generated_resources: dict | None = None,
    agent_trace: list | None = None,
    student_profile: dict | None = None,
    retrieved_sources: list | None = None,
    review_feedback: str | None = None,
) -> bool:
    now = time.time()

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")

        cursor.execute(
            """
            SELECT status,
                   generated_resources,
                   agent_trace,
                   student_profile,
                   retrieved_sources,
                   review_feedback
            FROM tasks
            WHERE task_id = ?
            """,
            (task_id,),
        )
        row = cursor.fetchone()

        if row is None:
            conn.rollback()
            return False

        if row["status"] not in {"pending", "running"}:
            conn.rollback()
            return False

        # Merge JSON fields
        existing_resources = json.loads(row["generated_resources"]) if row["generated_resources"] else {}
        if generated_resources:
            existing_resources.update(generated_resources)
        merged_resources_str = json.dumps(existing_resources, ensure_ascii=False)

        existing_trace = json.loads(row["agent_trace"]) if row["agent_trace"] else []
        if agent_trace:
            existing_trace.extend(agent_trace)
        merged_trace_str = json.dumps(existing_trace, ensure_ascii=False)

        existing_profile = json.loads(row["student_profile"]) if row["student_profile"] else {}
        if student_profile:
            existing_profile.update(student_profile)
        merged_profile_str = json.dumps(existing_profile, ensure_ascii=False)

        if retrieved_sources is not None:
            merged_sources_str = json.dumps(retrieved_sources, ensure_ascii=False)
        else:
            merged_sources_str = row["retrieved_sources"]

        if review_feedback is not None:
            merged_review = review_feedback
        else:
            merged_review = row["review_feedback"]

        cursor.execute(
            """
            UPDATE tasks
            SET progress = COALESCE(?, progress),
                current_stage = COALESCE(?, current_stage),
                generated_resources = ?,
                agent_trace = ?,
                student_profile = ?,
                retrieved_sources = ?,
                review_feedback = ?,
                heartbeat_at = ?,
                updated_at = ?
            WHERE task_id = ?
              AND status IN ('pending', 'running')
            """,
            (
                progress,
                current_stage,
                merged_resources_str,
                merged_trace_str,
                merged_profile_str,
                merged_sources_str,
                merged_review,
                now,
                now,
                task_id,
            ),
        )

        if cursor.rowcount != 1:
            conn.rollback()
            return False

        conn.commit()
        return True
def complete_task(task_id: str, *, resources: dict) -> bool:
    now = time.time()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE tasks
            SET status = 'completed',
                progress = 100,
                generated_resources = ?,
                current_stage = '任务已完成',
                completed_at = ?,
                updated_at = ?
            WHERE task_id = ?
              AND status IN ('pending', 'running')
            """,
            (json.dumps(resources, ensure_ascii=False), now, now, task_id),
        )
        rowcount = cursor.rowcount
        conn.commit()
        return rowcount == 1

def fail_task(
    task_id: str,
    *,
    stage: str,
    error: str,
) -> bool:
    now = time.time()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE tasks
            SET status = 'failed',
                progress = 100,
                current_stage = ?,
                error = ?,
                completed_at = ?,
                updated_at = ?
            WHERE task_id = ?
              AND status IN ('pending', 'running')
            """,
            (stage, error, now, now, task_id),
        )
        rowcount = cursor.rowcount
        conn.commit()
        return rowcount == 1

def finish_cancelled_task(task_id: str) -> bool:
    now = time.time()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE tasks
            SET status = 'cancelled',
                current_stage = '任务已取消',
                completed_at = ?,
                updated_at = ?
            WHERE task_id = ?
              AND status = 'cancel_requested'
            """,
            (now, now, task_id),
        )
        rowcount = cursor.rowcount
        conn.commit()
        return rowcount == 1

def expire_task(
    task_id: str,
    *,
    reason: str = "任务执行超时",
) -> bool:
    now = time.time()

    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE tasks
            SET status = 'expired',
                current_stage = ?,
                error = ?,
                completed_at = ?,
                updated_at = ?
            WHERE task_id = ?
              AND status IN ('pending', 'running')
            """,
            (
                reason,
                reason,
                now,
                now,
                task_id,
            ),
        )
        conn.commit()
        return cursor.rowcount == 1

def finalize_active_task_metadata(
    task_id: str,
    *,
    task_title: str | None = None,
    student_profile: dict | None = None,
    agent_trace: list | None = None,
    replace_agent_trace: bool = False,
    retrieved_sources: list | None = None,
    review_feedback: str | dict | None = None,
    conversation_summary: str | None = None,
) -> bool:
    now = time.time()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")

        cursor.execute(
            """
            SELECT status,
                   student_profile,
                   agent_trace
            FROM tasks
            WHERE task_id = ?
            """,
            (task_id,),
        )
        row = cursor.fetchone()

        if row is None:
            conn.rollback()
            return False

        if row["status"] not in {"pending", "running"}:
            conn.rollback()
            return False

        updates = {"updated_at": now}

        if task_title is not None:
            updates["task_title"] = task_title

        if conversation_summary is not None:
            updates["conversation_summary"] = conversation_summary

        if student_profile is not None:
            existing_profile = json.loads(row["student_profile"]) if row["student_profile"] else {}
            existing_profile.update(student_profile)
            updates["student_profile"] = json.dumps(existing_profile, ensure_ascii=False)

        if agent_trace is not None:
            if replace_agent_trace:
                updates["agent_trace"] = json.dumps(agent_trace, ensure_ascii=False)
            else:
                existing_trace = json.loads(row["agent_trace"]) if row["agent_trace"] else []
                existing_trace.extend(agent_trace)
                updates["agent_trace"] = json.dumps(existing_trace, ensure_ascii=False)

        if retrieved_sources is not None:
            updates["retrieved_sources"] = json.dumps(retrieved_sources, ensure_ascii=False)

        if review_feedback is not None:
            if isinstance(review_feedback, (dict, list)):
                updates["review_feedback"] = json.dumps(review_feedback, ensure_ascii=False)
            else:
                updates["review_feedback"] = review_feedback

        set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
        values = list(updates.values()) + [task_id]

        cursor.execute(
            f"""
            UPDATE tasks
            SET {set_clause}
            WHERE task_id = ?
              AND status IN ('pending', 'running')
            """,
            values,
        )

        if cursor.rowcount != 1:
            conn.rollback()
            return False

        conn.commit()
        return True

def refresh_task_heartbeat(task_id: str):
    now = time.time()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE tasks
            SET heartbeat_at = ?,
                updated_at = ?
            WHERE task_id = ?
              AND status IN ('pending', 'running')
            """,
            (now, now, task_id)
        )
        conn.commit()

@contextmanager
def task_heartbeat_guard(task_id: str, interval_seconds: int = 30):
    stop_event = Event()

    def heartbeat_loop():
        while not stop_event.wait(interval_seconds):
            refresh_task_heartbeat(task_id)

    thread = Thread(
        target=heartbeat_loop,
        daemon=True,
        name=f"task-heartbeat-{task_id}",
    )
    thread.start()

    try:
        yield
    finally:
        stop_event.set()
        thread.join(timeout=2)
