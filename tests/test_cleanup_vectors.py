import pytest
import time
from src.knowledge.repository import (
    create_knowledge_document,
    create_index_task,
    record_index_vectors
)
from src.db.database import get_connection
from src.knowledge.service import cleanup_failed_index_vectors

@pytest.fixture(autouse=True)
def clean_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM knowledge_chunks")
        cursor.execute("DELETE FROM knowledge_index_tasks")
        cursor.execute("DELETE FROM knowledge_documents")
        cursor.execute("DELETE FROM knowledge_index_vectors")
        conn.commit()

def test_cleanup_failed_index_vectors_planned_crash(monkeypatch):
    # Setup document
    now = time.time()
    doc_id = "cleanup_crash_doc"
    create_knowledge_document({
        "document_id": doc_id,
        "user_id": "user_a",
        "scope": "personal",
        "original_filename": "test.txt",
        "stored_path": "data/knowledge_base/test_file.txt",
        "file_size": 100,
        "sha256": "hash1",
        "status": "failed",
        "created_at": now,
        "updated_at": now
    })
    
    # Create index task in 'failed' status
    task_id = "task_failed_crash"
    create_index_task({
        "index_task_id": task_id,
        "document_id": doc_id,
        "status": "failed",
        "error": "Task crashed before Chroma write finished",
        "target_index_version": 1,
        "created_at": now,
        "updated_at": now
    })
    
    # Record vectors as 'planned' in SQLite (simulating they were planned but crash happened before/during Chroma write)
    record_index_vectors(
        index_task_id=task_id,
        document_id=doc_id,
        index_version=1,
        vector_ids=["vec_planned_1"],
        state="planned"
    )
    
    # Mock Chroma vector store delete to raise 'ID not found' exception
    deleted_ids = []
    class MockVS:
        def delete(self, ids):
            # Simulate "not found" exception typical for deleting non-existent ID
            raise ValueError(f"Vector IDs {ids} not found in collection")
            
    # Mock the get_user_vectorstore to return our MockVS
    monkeypatch.setattr("src.rag.vector_store.get_user_vectorstore", lambda: MockVS())
    
    # Verify the vector record exists in database
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM knowledge_index_vectors WHERE index_task_id = ? AND vector_id = ?", (task_id, "vec_planned_1"))
        assert cursor.fetchone()[0] == 1
        
    # Execute cleanup
    cleanup_failed_index_vectors()
    
    # Since ID not found is treated as success, the tracking record should be deleted!
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM knowledge_index_vectors WHERE index_task_id = ? AND vector_id = ?", (task_id, "vec_planned_1"))
        assert cursor.fetchone()[0] == 0
