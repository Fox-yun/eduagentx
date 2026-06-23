import pytest
import os
import time
import uuid


from src.knowledge.repository import (
    create_knowledge_document,
    get_knowledge_document,
    update_knowledge_document,
    create_index_task,
    get_index_task,
    claim_index_task
)
from langchain_core.documents import Document
from src.knowledge.splitter import split_document

@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    test_db = "data/test_knowledge.db"
    try:
        if os.path.exists(test_db):
            os.remove(test_db)
    except OSError:
        pass
    monkeypatch.setenv("SQLITE_DB_PATH", test_db)
    from src.db.database import init_db
    init_db()
    yield
    try:
        if os.path.exists(test_db):
            os.remove(test_db)
    except OSError:
        pass

def test_knowledge_repository_crud():
    doc_id = str(uuid.uuid4())
    now = time.time()
    
    doc_data = {
        "document_id": doc_id,
        "user_id": "test_user",
        "scope": "personal",
        "original_filename": "test.pdf",
        "stored_path": "/tmp/test.pdf",
        "file_size": 1024,
        "sha256": "fake_hash",
        "status": "pending",
        "created_at": now,
        "updated_at": now
    }
    
    assert create_knowledge_document(doc_data) == True
    
    doc = get_knowledge_document(doc_id)
    assert doc is not None
    assert doc["user_id"] == "test_user"
    assert doc["status"] == "pending"
    
    update_knowledge_document(doc_id, {"status": "ready"})
    doc = get_knowledge_document(doc_id)
    assert doc["status"] == "ready"

def test_index_task_claim():
    doc_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    now = time.time()
    
    # Needs a doc first due to foreign key
    doc_data = {
        "document_id": doc_id,
        "user_id": "u1",
        "original_filename": "t.txt",
        "stored_path": "t.txt",
        "file_size": 1,
        "sha256": "hash",
        "status": "pending",
        "created_at": now,
        "updated_at": now
    }
    create_knowledge_document(doc_data)
    
    task_data = {
        "index_task_id": task_id,
        "document_id": doc_id,
        "status": "pending",
        "target_index_version": 1,
        "created_at": now,
        "updated_at": now
    }
    create_index_task(task_data)
    
    # Claim it
    assert claim_index_task(task_id, "worker-1") == True
    
    # Try claim again, should fail
    assert claim_index_task(task_id, "worker-2") == False
    
    task = get_index_task(task_id)
    assert task["status"] == "running"
    assert task["worker_id"] == "worker-1"

def test_split_document():
    doc1 = Document(page_content="This is sentence 1. This is sentence 2.", metadata={"page": 1})
    
    chunks = split_document(
        documents=[doc1],
        document_id="doc_123",
        user_id="u1",
        course_id="c1",
        conversation_id=None,
        scope="course",
        source_name="test.txt",
        chunk_size=15,
        chunk_overlap=0
    )
    
    assert len(chunks) > 1
    assert chunks[0].metadata["document_id"] == "doc_123"
    assert chunks[0].metadata["user_id"] == "u1"
    assert chunks[0].metadata["course_id"] == "c1"
    assert chunks[0].metadata["scope"] == "course"
    assert chunks[0].metadata["page"] == 1
    assert chunks[0].metadata["chunk_index"] == 0
    
    assert chunks[1].metadata["chunk_index"] == 1
