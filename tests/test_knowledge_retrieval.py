import os
import pytest
import time
from src.knowledge.repository import (
    create_knowledge_document,
    get_authorized_active_versions
)
from src.db.database import get_connection
from src.rag.vector_store import merge_retrieval_candidates

@pytest.fixture(autouse=True)
def setup_docs():
    # Insert multiple documents with different scopes, statuses, and users
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM knowledge_documents")
        conn.commit()
        
    now = time.time()
    
    # Doc 1: User A personal ready v1
    create_knowledge_document({
        "document_id": "doc_a_personal",
        "user_id": "user_a",
        "scope": "personal",
        "original_filename": "file_a.txt",
        "stored_path": "/path/file_a.txt",
        "file_size": 100,
        "sha256": "hash_a",
        "status": "ready",
        "active_index_version": 1,
        "created_at": now,
        "updated_at": now
    })
    
    # Doc 2: User A session-1 ready v2
    create_knowledge_document({
        "document_id": "doc_a_session_1",
        "user_id": "user_a",
        "conversation_id": "conv_1",
        "scope": "session",
        "original_filename": "file_b.txt",
        "stored_path": "/path/file_b.txt",
        "file_size": 100,
        "sha256": "hash_b",
        "status": "ready",
        "active_index_version": 2,
        "created_at": now,
        "updated_at": now
    })
    
    # Doc 3: User A session-2 reindexing v3
    create_knowledge_document({
        "document_id": "doc_a_session_2_reindexing",
        "user_id": "user_a",
        "conversation_id": "conv_2",
        "scope": "session",
        "original_filename": "file_c.txt",
        "stored_path": "/path/file_c.txt",
        "file_size": 100,
        "sha256": "hash_c",
        "status": "reindexing",
        "active_index_version": 3,
        "created_at": now,
        "updated_at": now
    })
    
    # Doc 4: User A session-2 indexing v0
    create_knowledge_document({
        "document_id": "doc_a_session_2_indexing",
        "user_id": "user_a",
        "conversation_id": "conv_2",
        "scope": "session",
        "original_filename": "file_d.txt",
        "stored_path": "/path/file_d.txt",
        "file_size": 100,
        "sha256": "hash_d",
        "status": "indexing",
        "active_index_version": 0,
        "created_at": now,
        "updated_at": now
    })
    
    # Doc 5: System scope ready v1
    create_knowledge_document({
        "document_id": "doc_system",
        "user_id": "system",
        "scope": "system",
        "original_filename": "file_sys.txt",
        "stored_path": "/path/file_sys.txt",
        "file_size": 100,
        "sha256": "hash_sys",
        "status": "ready",
        "active_index_version": 1,
        "created_at": now,
        "updated_at": now
    })
    
    # Doc 6: User B personal ready v1
    create_knowledge_document({
        "document_id": "doc_b_personal",
        "user_id": "user_b",
        "scope": "personal",
        "original_filename": "file_b_p.txt",
        "stored_path": "/path/file_b_p.txt",
        "file_size": 100,
        "sha256": "hash_b_p",
        "status": "ready",
        "active_index_version": 1,
        "created_at": now,
        "updated_at": now
    })

def test_scope_and_ownership_filters():
    document_ids = [
        "doc_a_personal",
        "doc_a_session_1",
        "doc_a_session_2_reindexing",
        "doc_a_session_2_indexing",
        "doc_system",
        "doc_b_personal"
    ]
    
    # User A query for conv_1 (Should see doc_a_personal, doc_a_session_1, and doc_system)
    res_1 = get_authorized_active_versions(document_ids, user_id="user_a", conversation_id="conv_1")
    assert "doc_a_personal" in res_1 and res_1["doc_a_personal"] == 1
    assert "doc_a_session_1" in res_1 and res_1["doc_a_session_1"] == 2
    assert "doc_system" in res_1 and res_1["doc_system"] == 1
    assert "doc_a_session_2_reindexing" not in res_1 # wrong conversation context
    assert "doc_b_personal" not in res_1 # wrong user
    assert "doc_a_session_2_indexing" not in res_1 # status is indexing, version is 0
    
    # User A query with empty conversation (Should only see doc_a_personal and doc_system)
    res_2 = get_authorized_active_versions(document_ids, user_id="user_a", conversation_id=None)
    assert "doc_a_personal" in res_2
    assert "doc_system" in res_2
    assert "doc_a_session_1" not in res_2 # no conversation ID supplied
    
    # User B query for conv_1 (Should see doc_b_personal and doc_system)
    res_3 = get_authorized_active_versions(document_ids, user_id="user_b", conversation_id="conv_1")
    assert "doc_b_personal" in res_3
    assert "doc_system" in res_3
    assert "doc_a_personal" not in res_3

def test_stale_chunks_filtering_in_rag():
    class MockDoc:
        def __init__(self, document_id, vector_id, index_version, content):
            self.page_content = content
            self.metadata = {
                "document_id": document_id,
                "vector_id": vector_id,
                "index_version": index_version
            }
            
    # Mock retrieval candidates containing both older version 1 and active version 2 chunks of doc_a_session_1
    candidates = [
        {
            "document": MockDoc("doc_a_session_1", "v1_chunk", 1, "stale content"),
            "score": 0.9
        },
        {
            "document": MockDoc("doc_a_session_1", "v2_chunk", 2, "active content"),
            "score": 0.8
        }
    ]
    
    # Call merge_retrieval_candidates
    results = merge_retrieval_candidates(
        candidates=candidates,
        final_k=5,
        max_per_document=5,
        max_context_chars=10000,
        user_id="user_a",
        conversation_id="conv_1"
    )
    
    # Results should only retain version 2 chunk and skip version 1 chunk
    assert len(results) == 1
    assert results[0].metadata["index_version"] == 2
    assert results[0].metadata["vector_id"] == "v2_chunk"
