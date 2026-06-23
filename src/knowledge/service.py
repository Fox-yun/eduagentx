import os
import time
import uuid
import logging
from concurrent.futures import ThreadPoolExecutor
import asyncio

from src.knowledge.repository import (
    get_knowledge_document,
    update_knowledge_document,
    get_index_task,
    update_index_task,
    claim_index_task,
    insert_knowledge_chunks,
    delete_knowledge_chunks_by_document
)
from src.knowledge.parser import parse_document
from src.knowledge.splitter import split_document
from src.knowledge.indexer import add_documents_to_vector_store, delete_documents_from_vector_store
from src.db.database import get_connection

logger = logging.getLogger(__name__)

WORKER_ID = f"worker-{uuid.uuid4().hex[:8]}"
executor = ThreadPoolExecutor(max_workers=2)

def process_index_task(index_task_id: str, document_id: str):
    """
    Background worker function to process an index task.
    """
    try:
        # Claim task
        if not claim_index_task(index_task_id, WORKER_ID):
            logger.info(f"Task {index_task_id} already claimed or not pending.")
            return

        update_index_task(index_task_id, {"current_stage": "开始解析文档", "progress": 10})
        
        doc = get_knowledge_document(document_id)
        if not doc:
            raise ValueError(f"Document {document_id} not found")

        old_active_version = doc.get("active_index_version", 0)
        is_reindex = doc["status"] == "reindexing"
        if not is_reindex:
            update_knowledge_document(document_id, {"status": "indexing"})

        task_rec = get_index_task(index_task_id)
        if not task_rec:
            raise ValueError(f"Task {index_task_id} not found")
        index_version = task_rec.get("target_index_version", 1)

        # Determine Vector Store
        if doc["scope"] == "system":
            from src.rag.vector_store import get_system_vectorstore
            vs = get_system_vectorstore()
        else:
            from src.rag.vector_store import get_user_vectorstore
            vs = get_user_vectorstore()

        # Parse Document
        try:
            update_index_task(index_task_id, {"current_stage": "解析文档内容", "progress": 20})
            documents = parse_document(doc["stored_path"], doc["file_extension"])
        except Exception as e:
            raise RuntimeError(f"解析文档失败: {e}")
            
        if not documents:
            raise RuntimeError("解析结果为空")

        # Split Document
        update_index_task(index_task_id, {"current_stage": "文档切块", "progress": 40})
        chunks = split_document(
            documents=documents,
            document_id=document_id,
            user_id=doc["user_id"],
            course_id=doc["course_id"],
            conversation_id=doc.get("conversation_id"),
            scope=doc["scope"],
            source_name=doc["original_filename"]
        )
        
        # Index into Vector Store
        update_index_task(index_task_id, {"current_stage": "向量化与建立索引", "progress": 60})
        
        inserted_vector_ids = []
        try:
            inserted_vector_ids = add_documents_to_vector_store(
                vectorstore=vs,
                index_task_id=index_task_id,
                document_id=document_id,
                index_version=index_version,
                chunks=chunks
            )
            
            # Save chunk metadata to database
            update_index_task(index_task_id, {"current_stage": "保存索引元数据", "progress": 80})
            
            chunks_data = []
            for i, chunk in enumerate(chunks):
                chunks_data.append({
                    "chunk_id": str(uuid.uuid4()),
                    "document_id": document_id,
                    "vector_id": inserted_vector_ids[i],
                    "page_number": chunk.metadata.get("page"),
                    "chunk_index": chunk.metadata.get("chunk_index", i),
                    "content_hash": chunk.metadata.get("content_hash"),
                    "index_version": index_version,
                    "created_at": time.time()
                })
                
            insert_knowledge_chunks(chunks_data)
            
            # Complete Task
            now = time.time()
            
            # Switch active version and commit using optimistic concurrency check
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("BEGIN IMMEDIATE")
                cursor.execute(
                    """
                    UPDATE knowledge_documents
                    SET active_index_version = ?,
                        status = 'ready',
                        error = NULL,
                        page_count = ?,
                        chunk_count = ?,
                        indexed_at = ?,
                        updated_at = ?
                    WHERE document_id = ?
                      AND active_index_version = ?
                    """,
                    (index_version, len(documents), len(chunks), now, now, document_id, old_active_version)
                )
                rowcount = cursor.rowcount
                conn.commit()
                
            if rowcount != 1:
                raise RuntimeError("并发重索引冲突，切换 active version 失败")
            
            from src.knowledge.repository import update_index_vectors_state
            update_index_vectors_state(index_task_id, inserted_vector_ids, "committed")
            
            update_index_task(index_task_id, {
                "status": "completed",
                "current_stage": "索引完成",
                "progress": 100,
                "completed_at": now
            })
            
            # Clean old versions asynchronously if this is a reindex
            if is_reindex:
                def clean_old_versions():
                    try:
                        from src.knowledge.repository import get_knowledge_chunks_by_document, delete_index_vector_records
                        all_chunks = get_knowledge_chunks_by_document(document_id)
                        old_vectors = [c["vector_id"] for c in all_chunks if c.get("index_version", 0) < index_version]
                        if old_vectors:
                            delete_documents_from_vector_store(vs, old_vectors)
                            with get_connection() as conn:
                                conn.execute("DELETE FROM knowledge_chunks WHERE document_id = ? AND index_version < ?", (document_id, index_version))
                                conn.commit()
                            delete_index_vector_records(document_id, old_vectors)
                    except Exception as clean_e:
                        logger.error(f"Failed to clean old versions for {document_id}: {clean_e}")
                
                executor.submit(clean_old_versions)
            
            logger.info(f"Successfully indexed document {document_id} with version {index_version}")
            
        except Exception as exc:
            rollback_errors = []
            if inserted_vector_ids:
                try:
                    delete_documents_from_vector_store(vs, inserted_vector_ids)
                except Exception as rollback_exc:
                    rollback_errors.append(str(rollback_exc))
            
            # Clean new chunks ONLY
            with get_connection() as conn:
                conn.execute("DELETE FROM knowledge_chunks WHERE document_id = ? AND index_version = ?", (document_id, index_version))
                conn.commit()
            
            error_message = str(exc)
            if rollback_errors:
                error_message += "；向量回滚失败：" + "; ".join(rollback_errors)
                
            raise RuntimeError(error_message)

    except Exception as e:
        logger.error(f"Failed to process index task {index_task_id}: {e}")
        now = time.time()
        update_index_task(index_task_id, {
            "status": "failed",
            "current_stage": "索引失败",
            "error": str(e),
            "completed_at": now
        })
        
        # If reindexing fails, rollback to ready status with the old version safely
        if old_active_version > 0:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE knowledge_documents
                    SET status = 'ready',
                        active_index_version = ?,
                        error = ?,
                        updated_at = ?
                    WHERE document_id = ?
                      AND (active_index_version = ? OR status = 'reindexing')
                    """,
                    (old_active_version, f"重新索引失败，继续使用旧版本 v{old_active_version}: {e}", time.time(), document_id, old_active_version)
                )
                conn.commit()
        else:
            update_knowledge_document(document_id, {
                "status": "failed",
                "error": str(e)
            })

def submit_index_task(index_task_id: str, document_id: str):
    """
    Submits a task to the ThreadPoolExecutor.
    """
    executor.submit(process_index_task, index_task_id, document_id)

def recover_indexing_tasks_on_startup() -> list:
    """
    Find running index tasks and set them to failed/pending for retry.
    Returns a list of dicts with 'index_task_id' and 'document_id' to submit.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        
        # 1. 超过最大重试次数的任务直接标记为 failed
        cursor.execute(
            """
            UPDATE knowledge_index_tasks
            SET status = 'failed',
                error = '超过最大重试次数',
                current_stage = '任务终止',
                worker_id = NULL
            WHERE status IN ('running', 'pending')
              AND attempt_count >= 3
            """
        )
        
        # 2. 还在允许重试范围内的运行任务变为 pending
        cursor.execute(
            """
            UPDATE knowledge_index_tasks
            SET status = 'pending',
                error = '服务重启，任务重新入队',
                current_stage = '准备重试',
                worker_id = NULL
            WHERE status = 'running'
              AND attempt_count < 3
            """
        )
        
        # 3. 获取所有需要提交的 pending 任务
        cursor.execute(
            """
            SELECT index_task_id, document_id 
            FROM knowledge_index_tasks 
            WHERE status = 'pending' AND attempt_count < 3
            """
        )
        rows = cursor.fetchall()
        tasks_to_submit = [{"index_task_id": r["index_task_id"], "document_id": r["document_id"]} for r in rows]
        
        # 将无活跃任务的 indexing / reindexing 状态标记为 failed
        cursor.execute(
            """
            UPDATE knowledge_documents
            SET status = 'failed',
                error = '服务重启，无有效索引任务'
            WHERE status IN ('indexing', 'reindexing')
              AND document_id NOT IN (
                  SELECT document_id FROM knowledge_index_tasks 
                  WHERE status IN ('pending', 'running')
              )
            """
        )
        
        # 将正在删除中的文档标记为 delete_failed
        cursor.execute(
            """
            UPDATE knowledge_documents
            SET status = 'delete_failed',
                error = '服务重启，删除任务中断'
            WHERE status = 'deleting'
            """
        )
        conn.commit()
        return tasks_to_submit

def delete_document_completely(document_id: str):
    """
    Deletes a document from the database, storage, and vector store.
    """
    doc = get_knowledge_document(document_id)
    if not doc:
        return
        
    if doc["status"] != "deleting":
        logger.warning(f"Document {document_id} status is not 'deleting' ({doc['status']}). Skipping background deletion.")
        return

    if doc["scope"] == "system":
        logger.warning(f"Refusing to delete system scope document {document_id} via user API.")
        return

    # 1. Delete from user vector store
    from src.rag.vector_store import get_user_vectorstore
    vs = get_user_vectorstore()
    
    from src.knowledge.repository import get_knowledge_chunks_by_document
    chunks = get_knowledge_chunks_by_document(document_id)
    vector_ids = [c["vector_id"] for c in chunks]
    
    if vector_ids:
        try:
            delete_documents_from_vector_store(vs, vector_ids)
        except Exception as e:
            logger.error(f"Failed to delete vectors for document {document_id}: {e}")
            update_knowledge_document(document_id, {
                "status": "delete_failed",
                "error": f"删除向量索引失败: {str(e)}"
            })
            return
            
    # 2. Delete chunks from db
    delete_knowledge_chunks_by_document(document_id)
    
    # 3. Delete tracking records
    with get_connection() as conn:
        conn.execute("DELETE FROM knowledge_index_vectors WHERE document_id = ?", (document_id,))
        conn.commit()
    
    # 4. Delete from filesystem
    file_delete_error = None
    if doc.get("stored_path") and os.path.exists(doc["stored_path"]):
        try:
            os.remove(doc["stored_path"])
        except Exception as e:
            logger.error(f"Failed to delete file {doc['stored_path']}: {e}")
            file_delete_error = "原始文件清理失败，等待后台清理"
            
    # 5. Mark as deleted in db
    update_knowledge_document(document_id, {
        "status": "deleted",
        "error": file_delete_error,
        "deleted_at": time.time()
    })

def cleanup_failed_index_vectors():
    """
    Cleans up vectors in vector store that were planned/inserted but not committed,
    for tasks that have failed or were cancelled.
    """
    try:
        from src.rag.vector_store import get_system_vectorstore, get_user_vectorstore
        sys_vs = get_system_vectorstore()
        user_vs = get_user_vectorstore()
        
        with get_connection() as conn:
            cursor = conn.cursor()
            # Find vectors that are not committed, and their task is failed
            cursor.execute(
                """
                SELECT v.vector_id, d.scope, v.index_task_id
                FROM knowledge_index_vectors v
                JOIN knowledge_index_tasks t ON v.index_task_id = t.index_task_id
                JOIN knowledge_documents d ON v.document_id = d.document_id
                WHERE v.state IN ('planned', 'inserted')
                  AND t.status = 'failed'
                  AND v.cleanup_attempt_count < 3
                """
            )
            rows = cursor.fetchall()
            
            for row in rows:
                vector_id = row["vector_id"]
                scope = row["scope"]
                task_id = row["index_task_id"]
                vs = sys_vs if scope == "system" else user_vs
                
                try:
                    vs.delete(ids=[vector_id])
                    # If successful, delete the vector record
                    conn.execute("DELETE FROM knowledge_index_vectors WHERE index_task_id = ? AND vector_id = ?", (task_id, vector_id))
                except Exception as e:
                    err_msg = str(e).lower()
                    if "does not exist" in err_msg or "not found" in err_msg:
                         # Already deleted or never inserted
                        conn.execute("DELETE FROM knowledge_index_vectors WHERE index_task_id = ? AND vector_id = ?", (task_id, vector_id))
                    else:
                        conn.execute(
                            """
                            UPDATE knowledge_index_vectors 
                            SET cleanup_attempt_count = cleanup_attempt_count + 1,
                                state = CASE WHEN cleanup_attempt_count + 1 >= 3 THEN 'cleanup_failed' ELSE state END,
                                last_error = ? 
                            WHERE index_task_id = ? AND vector_id = ?
                            """,
                            (str(e), task_id, vector_id)
                        )
            conn.commit()
    except Exception as e:
        logger.error(f"Cleanup failed index vectors encountered an error: {e}")

