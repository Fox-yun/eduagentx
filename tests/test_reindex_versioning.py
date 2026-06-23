import os
import pytest
import time
import sqlite3
from src.knowledge.repository import (
    create_knowledge_document,
    get_knowledge_document,
    create_index_task,
    get_index_task,
    insert_knowledge_chunks,
    get_knowledge_chunks_by_document
)
from src.db.database import get_connection
from src.knowledge.service import process_index_task

@pytest.fixture(autouse=True)
def clean_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM knowledge_chunks")
        cursor.execute("DELETE FROM knowledge_index_tasks")
        cursor.execute("DELETE FROM knowledge_documents")
        cursor.execute("DELETE FROM knowledge_index_vectors")
        conn.commit()

def test_reindex_success_switch(monkeypatch):
    # Setup initial ready document v1
    now = time.time()
    doc_id = "reindex_success_doc"
    create_knowledge_document({
        "document_id": doc_id,
        "user_id": "user_a",
        "scope": "personal",
        "original_filename": "test.txt",
        "stored_path": "data/knowledge_base/test_file.txt",
        "file_size": 100,
        "sha256": "hash1",
        "status": "ready",
        "active_index_version": 1,
        "created_at": now,
        "updated_at": now
    })
    # Initial chunk v1
    insert_knowledge_chunks([{
        "chunk_id": "chunk_v1",
        "document_id": doc_id,
        "vector_id": "vec_v1",
        "chunk_index": 0,
        "index_version": 1,
        "created_at": now
    }])
    
    # Create re-indexing task: target version = 2
    task_id = "task_reindex_2"
    create_index_task({
        "index_task_id": task_id,
        "document_id": doc_id,
        "status": "pending",
        "target_index_version": 2,
        "created_at": now,
        "updated_at": now
    })
    
    # Mock parse and split to return fake objects
    class MockDoc:
        page_content = "updated text content"
        metadata = {"page": 0, "chunk_index": 0}
        
    monkeypatch.setattr("src.knowledge.service.parse_document", lambda *a, **k: [MockDoc()])
    monkeypatch.setattr("src.knowledge.service.split_document", lambda *a, **k: [MockDoc()])
    
    # Mock Chroma add & delete
    added_ids = []
    deleted_ids = []
    
    class MockVS:
        def add_documents(self, documents, ids):
            added_ids.extend(ids)
        def delete(self, ids):
            deleted_ids.extend(ids)
            
    monkeypatch.setattr("src.knowledge.service.add_documents_to_vector_store", lambda *a, **k: [f"{doc_id}:v2:0"])
    monkeypatch.setattr("src.knowledge.service.delete_documents_from_vector_store", lambda vs, ids: deleted_ids.extend(ids))
    
    # Set status to reindexing prior to worker running
    with get_connection() as conn:
        conn.execute("UPDATE knowledge_documents SET status = 'reindexing' WHERE document_id = ?", (doc_id,))
        conn.commit()
        
    # Execute task
    process_index_task(task_id, doc_id)
    
    # Verify status is ready, version is 2
    doc = get_knowledge_document(doc_id)
    assert doc["status"] == "ready"
    assert doc["active_index_version"] == 2
    assert doc["error"] is None
    
    # Old chunks and tracking vectors should have been deleted (wait, async deletes run in executor, wait 100ms)
    time.sleep(0.2)
    chunks = get_knowledge_chunks_by_document(doc_id)
    # Only v2 chunk remains
    assert len(chunks) == 1
    assert chunks[0]["index_version"] == 2
    
    # Check old vector ID is deleted
    assert "vec_v1" in deleted_ids

def test_reindex_failure_fallback(monkeypatch):
    # Setup initial ready document v1
    now = time.time()
    doc_id = "reindex_fail_doc"
    create_knowledge_document({
        "document_id": doc_id,
        "user_id": "user_a",
        "scope": "personal",
        "original_filename": "test.txt",
        "stored_path": "data/knowledge_base/test_file.txt",
        "file_size": 100,
        "sha256": "hash1",
        "status": "ready",
        "active_index_version": 1,
        "created_at": now,
        "updated_at": now
    })
    
    # Create re-indexing task: target version = 2
    task_id = "task_reindex_fail"
    create_index_task({
        "index_task_id": task_id,
        "document_id": doc_id,
        "status": "pending",
        "target_index_version": 2,
        "created_at": now,
        "updated_at": now
    })
    
    # Simulate parse document failure
    def mock_parse_fail(*args, **kwargs):
        raise RuntimeError("Parsing parsing failed!")
        
    monkeypatch.setattr("src.knowledge.service.parse_document", mock_parse_fail)
    
    # Set status to reindexing prior to worker running
    with get_connection() as conn:
        conn.execute("UPDATE knowledge_documents SET status = 'reindexing' WHERE document_id = ?", (doc_id,))
        conn.commit()
        
    # Execute task
    process_index_task(task_id, doc_id)
    
    # Verify status rolled back to ready, and active_index_version remains 1
    doc = get_knowledge_document(doc_id)
    assert doc["status"] == "ready"
    assert doc["active_index_version"] == 1
    assert "Parsing parsing failed!" in doc["error"]

def test_optimistic_switch_collision(monkeypatch):
    # Setup initial ready document v1
    now = time.time()
    doc_id = "reindex_collision_doc"
    create_knowledge_document({
        "document_id": doc_id,
        "user_id": "user_a",
        "scope": "personal",
        "original_filename": "test.txt",
        "stored_path": "data/knowledge_base/test_file.txt",
        "file_size": 100,
        "sha256": "hash1",
        "status": "ready",
        "active_index_version": 1,
        "created_at": now,
        "updated_at": now
    })
    
    # Create re-indexing task: target version = 2
    task_id = "task_reindex_collision"
    create_index_task({
        "index_task_id": task_id,
        "document_id": doc_id,
        "status": "pending",
        "target_index_version": 2,
        "created_at": now,
        "updated_at": now
    })
    
    # Mock parse and split
    class MockDoc:
        page_content = "content"
        metadata = {"page": 0, "chunk_index": 0}
    monkeypatch.setattr("src.knowledge.service.parse_document", lambda *a, **k: [MockDoc()])
    monkeypatch.setattr("src.knowledge.service.split_document", lambda *a, **k: [MockDoc()])
    monkeypatch.setattr("src.knowledge.service.add_documents_to_vector_store", lambda *a, **k: ["vec_new"])
    
    # Prior to switch step, let's simulate another process successfully switched version to 3
    # We do this by patching get_connection or adding code to intercept and change version
    # Let's directly intercept the database state
    def mock_add_with_version_change(*args, **kwargs):
        with get_connection() as conn:
            # Change doc version to 3 and status to ready behind the worker's back!
            conn.execute("UPDATE knowledge_documents SET active_index_version = 3, status = 'ready' WHERE document_id = ?", (doc_id,))
            conn.commit()
        return ["vec_new"]
    monkeypatch.setattr("src.knowledge.service.add_documents_to_vector_store", mock_add_with_version_change)
    
    # Set status to reindexing
    with get_connection() as conn:
        conn.execute("UPDATE knowledge_documents SET status = 'reindexing' WHERE document_id = ?", (doc_id,))
        conn.commit()
        
    # Execute task
    process_index_task(task_id, doc_id)
    
    # The task should fail at the switch step due to mismatch (WHERE active_index_version = 1 but it was 3)
    # The error rollback should set status back to ready and preserve version 3!
    doc = get_knowledge_document(doc_id)
    assert doc["status"] == "ready"
    assert doc["active_index_version"] == 3
    assert doc["error"] is None

def test_concurrent_switch_collision(monkeypatch):
    # Setup initial ready document v1
    now = time.time()
    doc_id = "concurrent_collision_doc"
    create_knowledge_document({
        "document_id": doc_id,
        "user_id": "user_a",
        "scope": "personal",
        "original_filename": "test.txt",
        "stored_path": "data/knowledge_base/test_file.txt",
        "file_size": 100,
        "sha256": "hash1",
        "status": "ready",
        "active_index_version": 1,
        "created_at": now,
        "updated_at": now
    })
    
    # Create Task B: target version = 2
    task_id = "task_reindex_B"
    create_index_task({
        "index_task_id": task_id,
        "document_id": doc_id,
        "status": "pending",
        "target_index_version": 2,
        "created_at": now,
        "updated_at": now
    })
    
    # Mock parse and split
    class MockDoc:
        page_content = "content"
        metadata = {"page": 0, "chunk_index": 0}
    monkeypatch.setattr("src.knowledge.service.parse_document", lambda *a, **k: [MockDoc()])
    monkeypatch.setattr("src.knowledge.service.split_document", lambda *a, **k: [MockDoc()])
    
    # Task A runs first and successfully switches to version 2 behind B's back during B's embedding/indexing phase
    def mock_add_with_version_switch(*args, **kwargs):
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE knowledge_documents 
                SET active_index_version = 2, status = 'ready', updated_at = ? 
                WHERE document_id = ?
                """,
                (time.time(), doc_id)
            )
            conn.commit()
        return ["vec_new_B"]
        
    monkeypatch.setattr("src.knowledge.service.add_documents_to_vector_store", mock_add_with_version_switch)
    
    # Set status to reindexing
    with get_connection() as conn:
        conn.execute("UPDATE knowledge_documents SET status = 'reindexing' WHERE document_id = ?", (doc_id,))
        conn.commit()
        
    # Execute Task B
    process_index_task(task_id, doc_id)
    
    # B should fail to switch and should not overwrite A's version 2 switch (meaning status remains ready, version remains 2)
    doc = get_knowledge_document(doc_id)
    assert doc["status"] == "ready"
    assert doc["active_index_version"] == 2
    
    # Task B should have status = failed
    task = get_index_task(task_id)
    assert task["status"] == "failed"
    assert "并发重索引冲突" in task["error"]
