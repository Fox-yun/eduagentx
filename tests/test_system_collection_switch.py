import os
import time
import pytest
import sqlite3
from scripts.rebuild_system_knowledge import rebuild_system_knowledge
from src.db.database import get_connection

@pytest.fixture(autouse=True)
def clean_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM knowledge_system_builds")
        cursor.execute("DELETE FROM knowledge_chunks")
        cursor.execute("DELETE FROM knowledge_documents")
        cursor.execute("DELETE FROM knowledge_settings WHERE setting_key = 'active_system_collection'")
        conn.commit()

def test_dry_run_no_writes(monkeypatch):
    # Setup mock files
    monkeypatch.setattr("os.listdir", lambda *a: ["sample.txt"])
    monkeypatch.setattr("os.path.isfile", lambda *a: True)
    monkeypatch.setattr("os.path.getsize", lambda *a: 100)
    
    # Mock parse and split
    class MockDoc:
        page_content = "text"
        metadata = {}
    monkeypatch.setattr("scripts.rebuild_system_knowledge.parse_document", lambda *a: [MockDoc()])
    monkeypatch.setattr("scripts.rebuild_system_knowledge.split_document", lambda *a, **k: [MockDoc()])
    
    # Run dry run
    rebuild_system_knowledge(dry_run=True, reset=False, purge_old=False, keep_last=2, confirm=False)
    
    # Assert database is empty
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM knowledge_system_builds")
        assert cursor.fetchone()[0] == 0
        cursor.execute("SELECT COUNT(*) FROM knowledge_documents")
        assert cursor.fetchone()[0] == 0

def test_reset_validation_failure_cleanup(monkeypatch):
    # Setup mock files
    monkeypatch.setattr("os.listdir", lambda *a: ["sample.txt"])
    monkeypatch.setattr("os.path.isfile", lambda *a: True)
    monkeypatch.setattr("os.path.getsize", lambda *a: 100)
    
    class MockDoc:
        page_content = "system text"
        metadata = {"page": 0, "chunk_index": 0}
    monkeypatch.setattr("scripts.rebuild_system_knowledge.parse_document", lambda *a: [MockDoc()])
    monkeypatch.setattr("scripts.rebuild_system_knowledge.split_document", lambda *a, **k: [MockDoc()])
    
    # Mock vector store addition but trigger validation failure by making Chroma count mismatch
    deleted_collections = []
    
    class MockCollection:
        def count(self):
            return 9999 # Mismatch!
        def get(self, ids):
            return {"ids": []}
        def delete_collection(self, name):
            deleted_collections.append(name)
            
    class MockVS:
        _collection = MockCollection()
        _client = MockCollection()
        def add_documents(self, documents, ids):
            pass
            
    # Mock get_vectorstore
    monkeypatch.setattr("scripts.rebuild_system_knowledge.get_vectorstore", lambda *a: MockVS())
    
    # Run reset (should fail at validation and clean up new Chroma collection)
    rebuild_system_knowledge(dry_run=False, reset=True, purge_old=False, keep_last=2, confirm=False)
    
    # Verify build status is failed in database
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status, error FROM knowledge_system_builds")
        row = cursor.fetchone()
        assert row[0] == "failed"
        assert "mismatch" in row[1]
        
        # Verify SQLite active collection setting is NOT updated
        cursor.execute("SELECT setting_value FROM knowledge_settings WHERE setting_key = 'active_system_collection'")
        assert cursor.fetchone() is None
        
    # Check new collection was deleted from Chroma
    assert len(deleted_collections) == 1
    assert "system_knowledge_v" in deleted_collections[0]

def test_purge_old_partially_fails(monkeypatch):
    now = time.time()
    
    # 1. Setup SQLite active settings and builds
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO knowledge_settings (setting_key, setting_value, updated_at) VALUES ('active_system_collection', 'system_knowledge_v2_active', ?)",
            (now,)
        )
        # Build 2: active
        cursor.execute(
            "INSERT INTO knowledge_system_builds (collection_name, index_version, status, created_at) VALUES ('system_knowledge_v2_active', 2, 'active', ?)",
            (now,)
        )
        # Build 1: retired
        cursor.execute(
            "INSERT INTO knowledge_system_builds (collection_name, index_version, status, created_at) VALUES ('system_knowledge_v1_retired', 1, 'retired', ?)",
            (now,)
        )
        # Build 0: failed
        cursor.execute(
            "INSERT INTO knowledge_system_builds (collection_name, index_version, status, created_at) VALUES ('system_knowledge_v0_failed', 0, 'failed', ?)",
            (now,)
        )
        
        # Insert a system document
        cursor.execute(
            """
            INSERT INTO knowledge_documents (document_id, user_id, scope, original_filename, stored_path, file_size, sha256, status, created_at, updated_at)
            VALUES ('sys_doc', 'system', 'system', 'sys.pdf', 'fake.pdf', 100, 'sys_hash', 'ready', ?, ?)
            """,
            (now, now)
        )
        
        # Insert chunks for version 1 and 0
        cursor.execute(
            "INSERT INTO knowledge_chunks (chunk_id, document_id, vector_id, chunk_index, index_version, created_at) VALUES ('c_v1', 'sys_doc', 'vec_v1', 0, 1, ?)",
            (now,)
        )
        cursor.execute(
            "INSERT INTO knowledge_chunks (chunk_id, document_id, vector_id, chunk_index, index_version, created_at) VALUES ('c_v0', 'sys_doc', 'vec_v0', 0, 0, ?)",
            (now,)
        )
        conn.commit()

    # 2. Mock Vector Store so that deleting v1 throws error, but v0 succeeds
    deleted_collections = []
    
    class MockClient:
        def delete_collection(self, name):
            if name == "system_knowledge_v1_retired":
                raise Exception("Chroma connection timed out")
            deleted_collections.append(name)
            
    class MockVS:
        _client = MockClient()
        def __init__(self, col_name):
            self.col_name = col_name
            
    # Mock get_vectorstore to return MockVS
    monkeypatch.setattr("scripts.rebuild_system_knowledge.get_vectorstore", lambda db_path, col_name: MockVS(col_name))
    
    # 3. Run purge with keep_last=0 (meaning we want to purge v1 and v0), with confirm=True
    rebuild_system_knowledge(dry_run=False, reset=False, purge_old=True, keep_last=0, confirm=True)
    
    # 4. Verify SQLite state
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # v2 active should remain untouched
        cursor.execute("SELECT status FROM knowledge_system_builds WHERE collection_name = 'system_knowledge_v2_active'")
        assert cursor.fetchone()["status"] == "active"
        
        # v1 retired delete failed in Chroma, so SQLite build status must remain 'retired' and chunk remains
        cursor.execute("SELECT status FROM knowledge_system_builds WHERE collection_name = 'system_knowledge_v1_retired'")
        assert cursor.fetchone()["status"] == "retired"
        cursor.execute("SELECT COUNT(*) FROM knowledge_chunks WHERE index_version = 1")
        assert cursor.fetchone()[0] == 1
        
        # v0 failed delete succeeded in Chroma, so SQLite build status must become 'purged' and chunk is deleted
        cursor.execute("SELECT status FROM knowledge_system_builds WHERE collection_name = 'system_knowledge_v0_failed'")
        assert cursor.fetchone()["status"] == "purged"
        cursor.execute("SELECT COUNT(*) FROM knowledge_chunks WHERE index_version = 0")
        assert cursor.fetchone()[0] == 0
        
    assert "system_knowledge_v0_failed" in deleted_collections
    assert "system_knowledge_v1_retired" not in deleted_collections
