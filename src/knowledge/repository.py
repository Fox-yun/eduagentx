import time
from typing import List, Dict, Any, Optional
from src.db.database import get_connection
from src.knowledge.models import KnowledgeDocumentInternal, KnowledgeIndexTaskSchema

def create_knowledge_document(doc_data: dict) -> bool:
    with get_connection() as conn:
        try:
            cursor = conn.cursor()
            cols = ", ".join(doc_data.keys())
            placeholders = ", ".join(["?"] * len(doc_data))
            cursor.execute(
                f"INSERT INTO knowledge_documents ({cols}) VALUES ({placeholders})",
                list(doc_data.values())
            )
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise

def get_knowledge_document(document_id: str) -> Optional[dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM knowledge_documents WHERE document_id = ? AND status != 'deleted'", (document_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

def update_knowledge_document(document_id: str, updates: dict) -> bool:
    if not updates:
        return True
    now = time.time()
    updates["updated_at"] = now
    
    with get_connection() as conn:
        cursor = conn.cursor()
        set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
        values = list(updates.values()) + [document_id]
        cursor.execute(
            f"UPDATE knowledge_documents SET {set_clause} WHERE document_id = ?",
            values
        )
        conn.commit()
        return cursor.rowcount > 0

def list_knowledge_documents(
    user_id: str,
    course_id: Optional[str] = None,
    scope: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 20,
    offset: int = 0
) -> tuple[List[dict], int]:
    query_base = """
        FROM knowledge_documents kd
        LEFT JOIN knowledge_index_tasks kit
          ON kit.index_task_id = (
              SELECT kit2.index_task_id
              FROM knowledge_index_tasks kit2
              WHERE kit2.document_id = kd.document_id
              ORDER BY kit2.created_at DESC
              LIMIT 1
          )
        WHERE kd.status != 'deleted'
    """
    
    query = "SELECT kd.*, kit.index_task_id, kit.status as index_status, kit.progress as index_progress, kit.current_stage as index_stage, kit.error as index_error " + query_base
    count_query = "SELECT COUNT(*) as total " + query_base
    
    params = []
    
    # user_id is mandatory, but include system scope
    query += " AND (kd.user_id = ? OR kd.scope = 'system')"
    count_query += " AND (kd.user_id = ? OR kd.scope = 'system')"
    params.append(user_id)
        
    if course_id == "__none__":
        query += " AND (kd.course_id IS NULL OR kd.course_id = '')"
        count_query += " AND (kd.course_id IS NULL OR kd.course_id = '')"
    elif course_id not in (None, "__all__"):
        query += " AND kd.course_id = ?"
        count_query += " AND kd.course_id = ?"
        params.append(course_id)
        
    if scope:
        query += " AND kd.scope = ?"
        count_query += " AND kd.scope = ?"
        params.append(scope)
        
    if status:
        query += " AND kd.status = ?"
        count_query += " AND kd.status = ?"
        params.append(status)
        
    query += " ORDER BY kd.created_at DESC LIMIT ? OFFSET ?"
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute(count_query, params)
        total = cursor.fetchone()["total"]
        
        cursor.execute(query, params + [limit, offset])
        rows = cursor.fetchall()
        
        return [dict(row) for row in rows], total

def get_authorized_active_versions(
    document_ids: List[str],
    user_id: str,
    conversation_id: Optional[str] = None
) -> dict[str, int]:
    if not document_ids:
        return {}
        
    with get_connection() as conn:
        cursor = conn.cursor()
        placeholders = ",".join(["?"] * len(document_ids))
        
        query = f"""
            SELECT document_id, active_index_version
            FROM knowledge_documents 
            WHERE document_id IN ({placeholders}) 
              AND (status = 'ready' OR (status = 'reindexing' AND active_index_version > 0))
        """
        
        authorization_conditions = [
            "scope = 'system'",
            "(scope = 'personal' AND user_id = ?)"
        ]
        params = list(document_ids) + [user_id]
        
        if conversation_id:
            authorization_conditions.append("(scope = 'session' AND user_id = ? AND conversation_id = ?)")
            params.extend([user_id, conversation_id])
            
        query += f" AND ({' OR '.join(authorization_conditions)})"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return {row["document_id"]: row["active_index_version"] for row in rows}

def claim_document_for_deletion(document_id: str, user_id: str) -> bool:
    now = time.time()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute(
            """
            UPDATE knowledge_documents
            SET status = 'deleting',
                updated_at = ?
            WHERE document_id = ?
              AND user_id = ?
              AND status IN ('ready', 'failed', 'delete_failed')
            """,
            (now, document_id, user_id)
        )
        rowcount = cursor.rowcount
        conn.commit()
        return rowcount == 1

def claim_document_for_reindex(document_id: str, user_id: str) -> bool:
    now = time.time()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute(
            """
            UPDATE knowledge_documents
            SET status = 'reindexing',
                updated_at = ?
            WHERE document_id = ?
              AND user_id = ?
              AND status IN ('ready', 'failed', 'delete_failed')
            """,
            (now, document_id, user_id)
        )
        rowcount = cursor.rowcount
        conn.commit()
        return rowcount == 1

def create_index_task(task_data: dict) -> bool:
    if "target_index_version" not in task_data or task_data["target_index_version"] < 1:
        raise ValueError("target_index_version must be explicitly specified and >= 1")
    with get_connection() as conn:
        try:
            cursor = conn.cursor()
            cols = ", ".join(task_data.keys())
            placeholders = ", ".join(["?"] * len(task_data))
            cursor.execute(
                f"INSERT INTO knowledge_index_tasks ({cols}) VALUES ({placeholders})",
                list(task_data.values())
            )
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise

def get_index_task(index_task_id: str) -> Optional[dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM knowledge_index_tasks WHERE index_task_id = ?", (index_task_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

def claim_index_task(index_task_id: str, worker_id: str) -> bool:
    now = time.time()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute(
            """
            UPDATE knowledge_index_tasks
            SET status = 'running',
                started_at = COALESCE(started_at, ?),
                updated_at = ?,
                heartbeat_at = ?,
                worker_id = ?,
                attempt_count = attempt_count + 1
            WHERE index_task_id = ? AND status = 'pending' AND attempt_count < 3
            """,
            (now, now, now, worker_id, index_task_id)
        )
        rowcount = cursor.rowcount
        conn.commit()
        return rowcount == 1

def update_index_task(index_task_id: str, updates: dict) -> bool:
    if not updates:
        return True
    now = time.time()
    updates["updated_at"] = now
    
    with get_connection() as conn:
        cursor = conn.cursor()
        set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
        values = list(updates.values()) + [index_task_id]
        cursor.execute(
            f"UPDATE knowledge_index_tasks SET {set_clause} WHERE index_task_id = ?",
            values
        )
        conn.commit()
        return cursor.rowcount > 0

def insert_knowledge_chunks(chunks_data: List[dict]) -> bool:
    if not chunks_data:
        return True
    
    with get_connection() as conn:
        try:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            
            for chunk in chunks_data:
                cols = ", ".join(chunk.keys())
                placeholders = ", ".join(["?"] * len(chunk))
                cursor.execute(
                    f"INSERT INTO knowledge_chunks ({cols}) VALUES ({placeholders})",
                    list(chunk.values())
                )
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise

def get_knowledge_chunks_by_document(document_id: str) -> List[dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM knowledge_chunks WHERE document_id = ?", (document_id,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def delete_knowledge_chunks_by_document(document_id: str) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM knowledge_chunks WHERE document_id = ?", (document_id,))
        conn.commit()
        return True

def record_index_vectors(index_task_id: str, document_id: str, index_version: int, vector_ids: List[str], state: str) -> bool:
    if not vector_ids:
        return True
    
    now = time.time()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        
        for vid in vector_ids:
            cursor.execute(
                """
                INSERT INTO knowledge_index_vectors 
                (index_task_id, document_id, index_version, vector_id, state, created_at, updated_at) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(index_task_id, vector_id) DO UPDATE SET 
                state=excluded.state, updated_at=excluded.updated_at
                """,
                (index_task_id, document_id, index_version, vid, state, now, now)
            )
        conn.commit()
        return True

def update_index_vectors_state(index_task_id: str, vector_ids: List[str], new_state: str) -> bool:
    if not vector_ids:
        return True
        
    now = time.time()
    with get_connection() as conn:
        cursor = conn.cursor()
        placeholders = ",".join(["?"] * len(vector_ids))
        cursor.execute(
            f"""
            UPDATE knowledge_index_vectors
            SET state = ?, updated_at = ?
            WHERE index_task_id = ? AND vector_id IN ({placeholders})
            """,
            [new_state, now, index_task_id] + vector_ids
        )
        conn.commit()
        return True

def delete_index_vector_records(document_id: str, vector_ids: list[str]) -> int:
    if not vector_ids:
        return 0
    with get_connection() as conn:
        placeholders = ",".join(["?"] * len(vector_ids))
        cursor = conn.cursor()
        cursor.execute(
            f"DELETE FROM knowledge_index_vectors WHERE document_id = ? AND vector_id IN ({placeholders})",
            [document_id] + vector_ids
        )
        conn.commit()
        return cursor.rowcount

