import os
import sqlite3
import pytest
import time

def create_old_schema_db(db_path: str):
    """
    Creates a database structure mimicking the schema prior to version columns migration.
    """
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # 1. Old tasks table
    c.execute('''
        CREATE TABLE tasks (
            task_id TEXT PRIMARY KEY,
            user_input TEXT,
            status TEXT,
            progress INTEGER,
            current_stage TEXT,
            task_title TEXT,
            student_profile TEXT,
            generated_resources TEXT,
            retrieved_sources TEXT,
            agent_trace TEXT,
            review_feedback TEXT,
            error TEXT,
            created_at REAL,
            updated_at REAL
        )
    ''')
    
    # 2. Old knowledge_documents (without active_index_version)
    c.execute('''
        CREATE TABLE knowledge_documents (
            document_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            course_id TEXT,
            conversation_id TEXT,
            scope TEXT NOT NULL DEFAULT 'personal',
            original_filename TEXT NOT NULL,
            display_name TEXT,
            stored_path TEXT NOT NULL,
            mime_type TEXT,
            file_extension TEXT,
            file_size INTEGER NOT NULL,
            sha256 TEXT NOT NULL,
            status TEXT NOT NULL,
            page_count INTEGER DEFAULT 0,
            chunk_count INTEGER DEFAULT 0,
            error TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            indexed_at REAL,
            deleted_at REAL
        )
    ''')
    
    # 3. Old knowledge_index_tasks (without target_index_version)
    c.execute('''
        CREATE TABLE knowledge_index_tasks (
            index_task_id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            status TEXT NOT NULL,
            progress INTEGER DEFAULT 0,
            current_stage TEXT,
            error TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            FOREIGN KEY(document_id) REFERENCES knowledge_documents(document_id)
        )
    ''')
    
    # 4. Old knowledge_chunks (without index_version)
    c.execute('''
        CREATE TABLE knowledge_chunks (
            chunk_id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            vector_id TEXT NOT NULL,
            page_number INTEGER,
            chunk_index INTEGER NOT NULL,
            content_hash TEXT,
            created_at REAL NOT NULL,
            FOREIGN KEY(document_id) REFERENCES knowledge_documents(document_id)
        )
    ''')
    
    conn.commit()
    return conn

def test_migrations_and_backfill(tmp_path):
    db_path = os.path.join(tmp_path, "test_migrations.db")
    conn = create_old_schema_db(db_path)
    c = conn.cursor()
    
    # Insert test data before migrations
    now = time.time()
    
    # Doc 1: ready with associated chunk -> Expect active_index_version = 1
    c.execute("""
        INSERT INTO knowledge_documents (document_id, user_id, original_filename, stored_path, file_size, sha256, status, created_at, updated_at)
        VALUES ('doc_with_chunk', 'user_1', 'file1.txt', '/path/file1.txt', 100, 'hash1', 'ready', ?, ?)
    """, (now, now))
    c.execute("""
        INSERT INTO knowledge_chunks (chunk_id, document_id, vector_id, chunk_index, created_at)
        VALUES ('chunk_1', 'doc_with_chunk', 'vec_1', 0, ?)
    """, (now,))
    
    # Doc 2: ready without any chunk -> Expect active_index_version = 0, status = failed
    c.execute("""
        INSERT INTO knowledge_documents (document_id, user_id, original_filename, stored_path, file_size, sha256, status, created_at, updated_at)
        VALUES ('doc_without_chunk', 'user_1', 'file2.txt', '/path/file2.txt', 200, 'hash2', 'ready', ?, ?)
    """, (now, now))
    
    # Doc 3: indexing with active task -> Task should be interrupted, doc status -> failed (version = 0)
    c.execute("""
        INSERT INTO knowledge_documents (document_id, user_id, original_filename, stored_path, file_size, sha256, status, created_at, updated_at)
        VALUES ('doc_indexing', 'user_1', 'file3.txt', '/path/file3.txt', 300, 'hash3', 'indexing', ?, ?)
    """, (now, now))
    c.execute("""
        INSERT INTO knowledge_index_tasks (index_task_id, document_id, status, created_at, updated_at)
        VALUES ('task_1', 'doc_indexing', 'running', ?, ?)
    """, (now, now))
    
    conn.commit()
    
    # Run migrations first time
    from src.db.migrations import run_migrations
    run_migrations(conn)
    
    # Verify migration results
    c.execute("PRAGMA table_info(knowledge_chunks)")
    chunks_cols = {row[1]: row for row in c.fetchall()}
    assert "index_version" in chunks_cols
    
    c.execute("PRAGMA table_info(knowledge_index_tasks)")
    tasks_cols = {row[1]: row for row in c.fetchall()}
    assert "target_index_version" in tasks_cols
    
    c.execute("PRAGMA table_info(knowledge_index_vectors)")
    vectors_cols = {row[1]: row for row in c.fetchall()}
    assert "index_version" in vectors_cols
    
    # Check backfilled values
    # Doc with chunk: active_index_version = 1
    c.execute("SELECT active_index_version, status, error FROM knowledge_documents WHERE document_id = 'doc_with_chunk'")
    row = c.fetchone()
    assert row[0] == 1
    assert row[1] == 'ready'
    assert row[2] is None
    
    # Doc without chunk: active_index_version = 0, status = failed, migration error set
    c.execute("SELECT active_index_version, status, error FROM knowledge_documents WHERE document_id = 'doc_without_chunk'")
    row = c.fetchone()
    assert row[0] == 0
    assert row[1] == 'failed'
    assert '迁移' in row[2]
    
    # Old running task should be interrupted, and doc indexing status should be failed
    c.execute("SELECT status, error FROM knowledge_index_tasks WHERE index_task_id = 'task_1'")
    row = c.fetchone()
    assert row[0] == 'interrupted'
    
    c.execute("SELECT status, error FROM knowledge_documents WHERE document_id = 'doc_indexing'")
    row = c.fetchone()
    assert row[0] == 'failed'
    assert '原索引任务' in row[1]
    
    # Verify indexes
    c.execute("SELECT name FROM sqlite_master WHERE type = 'index'")
    indexes = [r[0] for r in c.fetchall()]
    assert "idx_knowledge_chunks_document_version" in indexes
    assert "idx_system_builds_index_version" in indexes
    
    # Now simulate an intermediate state: active_index_version = 3, status = 'reindexing'
    # with a pending/running task, then re-run migrations
    c.execute("""
        UPDATE knowledge_documents 
        SET active_index_version = 3, status = 'reindexing' 
        WHERE document_id = 'doc_with_chunk'
    """)
    c.execute("""
        INSERT INTO knowledge_index_tasks (index_task_id, document_id, status, created_at, updated_at)
        VALUES ('task_reindex_old', 'doc_with_chunk', 'pending', ?, ?)
    """, (now, now))
    conn.commit()
    
    # Run migrations second time (idempotency/re-run check)
    run_migrations(conn)
    
    # Check that task_reindex_old is interrupted
    c.execute("SELECT status, error FROM knowledge_index_tasks WHERE index_task_id = 'task_reindex_old'")
    row = c.fetchone()
    assert row[0] == 'interrupted'
    
    # Check that doc_with_chunk recovered to ready with active_index_version = 3
    c.execute("SELECT active_index_version, status, error FROM knowledge_documents WHERE document_id = 'doc_with_chunk'")
    row = c.fetchone()
    assert row[0] == 3
    assert row[1] == 'ready'
    assert '原索引任务' in row[2]
    
    conn.close()
