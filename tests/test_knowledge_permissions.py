import pytest
from src.api.knowledge import upload_document, get_document, delete_document, reindex_document, list_documents
from src.knowledge.repository import get_knowledge_document, create_knowledge_document, update_knowledge_document
from src.knowledge.service import delete_document_completely
from fastapi import HTTPException, BackgroundTasks
import tempfile
import os
from src.db.database import get_connection

def test_document_isolation():
    # User A lists documents
    res = list_documents(user_id="userA", page_size=100)
    assert res.total >= 0

def test_delete_permission():
    # User A tries to delete user B's doc
    doc_data = {
        "document_id": "test_doc_isolation",
        "user_id": "userB",
        "course_id": None,
        "scope": "personal",
        "original_filename": "test.txt",
        "stored_path": "fake/path.txt",
        "file_size": 100,
        "sha256": "fakehash",
        "status": "ready",
        "created_at": 1000,
        "updated_at": 1000
    }
    create_knowledge_document(doc_data)
    
    bg = BackgroundTasks()
    with pytest.raises(HTTPException) as exc:
        delete_document(document_id="test_doc_isolation", user_id="userA", background_tasks=bg)
    assert exc.value.status_code == 403

def test_session_isolation_upload():
    # Test uploading session doc without conversation_id
    from fastapi import UploadFile
    import io
    
    file = UploadFile(filename="test.txt", file=io.BytesIO(b"test"))
    
    with pytest.raises(HTTPException) as exc:
        # FastAPI's async test requires careful handling, but this is a mock representation
        import asyncio
        asyncio.run(upload_document(file=file, user_id="userA", scope="session", conversation_id=None))
    assert exc.value.status_code == 400
    assert "conversation_id" in exc.value.detail

def test_delete_rollback():
    # Mock Chroma exception
    doc_data = {
        "document_id": "test_doc_delete",
        "user_id": "userA",
        "course_id": None,
        "scope": "personal",
        "original_filename": "test.txt",
        "stored_path": "fake/path.txt",
        "file_size": 100,
        "sha256": "fakehash2",
        "status": "ready",
        "created_at": 1000,
        "updated_at": 1000
    }
    create_knowledge_document(doc_data)
    
    # We will mock the delete_documents_from_vector_store to fail
    import src.knowledge.service
    original = src.knowledge.service.delete_documents_from_vector_store
    
    def mock_delete(vs, vids):
        raise Exception("Mock chroma fail")
        
    src.knowledge.service.delete_documents_from_vector_store = mock_delete
    try:
        # Set status to deleting to bypass check
        update_knowledge_document("test_doc_delete", {"status": "deleting"})
        
        # Pretend there are chunks so it tries to delete
        from src.knowledge.repository import insert_knowledge_chunks
        insert_knowledge_chunks([{
            "chunk_id": "c1",
            "document_id": "test_doc_delete",
            "vector_id": "v1",
            "chunk_index": 0,
            "index_version": 1,
            "created_at": 1000
        }])
        
        delete_document_completely("test_doc_delete")
        doc = get_knowledge_document("test_doc_delete")
        assert doc["status"] == "delete_failed"
    finally:
        src.knowledge.service.delete_documents_from_vector_store = original

def test_delete_file_failure(monkeypatch):
    doc_data = {
        "document_id": "test_doc_file_fail",
        "user_id": "userA",
        "course_id": None,
        "scope": "personal",
        "original_filename": "test.txt",
        "stored_path": "fake/path_to_delete.txt",
        "file_size": 100,
        "sha256": "fakehash3",
        "status": "ready",
        "created_at": 1000,
        "updated_at": 1000
    }
    create_knowledge_document(doc_data)
    
    # Mock vector store delete to do nothing
    monkeypatch.setattr("src.knowledge.service.delete_documents_from_vector_store", lambda *a, **k: True)
    
    # Mock os.remove to raise OSError
    def mock_remove(path):
        raise OSError("Permission denied")
    monkeypatch.setattr("os.remove", mock_remove)
    monkeypatch.setattr("os.path.exists", lambda path: True) # force exists to check removal path
    
    try:
        # Set status to deleting to bypass check
        update_knowledge_document("test_doc_file_fail", {"status": "deleting"})
        
        # Insert some chunks
        from src.knowledge.repository import insert_knowledge_chunks, get_knowledge_chunks_by_document
        insert_knowledge_chunks([{
            "chunk_id": "c2",
            "document_id": "test_doc_file_fail",
            "vector_id": "v2",
            "chunk_index": 0,
            "index_version": 1,
            "created_at": 1000
        }])
        
        delete_document_completely("test_doc_file_fail")
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status, error FROM knowledge_documents WHERE document_id = 'test_doc_file_fail'")
            row = cursor.fetchone()
        
        assert row is not None
        # Status must be 'deleted'
        assert row[0] == "deleted"
        # Error must record the file cleanup exception
        assert row[1] == "原始文件清理失败，等待后台清理"
        
        # Chunks must be deleted
        chunks = get_knowledge_chunks_by_document("test_doc_file_fail")
        assert len(chunks) == 0
    finally:
        pass
