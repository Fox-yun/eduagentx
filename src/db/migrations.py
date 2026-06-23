import sqlite3
from typing import List

def run_migrations(conn: sqlite3.Connection):
    """
    Idempotent database migrations for the Knowledge Base module.
    """
    c = conn.cursor()

    # 1. Create knowledge_settings table
    c.execute('''
        CREATE TABLE IF NOT EXISTS knowledge_settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT NOT NULL,
            updated_at REAL NOT NULL
        )
    ''')

    # 2. Create knowledge_index_vectors table
    c.execute('''
        CREATE TABLE IF NOT EXISTS knowledge_index_vectors (
            index_task_id TEXT NOT NULL,
            document_id TEXT NOT NULL,
            index_version INTEGER NOT NULL,
            vector_id TEXT NOT NULL,
            state TEXT NOT NULL,
            cleanup_attempt_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            PRIMARY KEY(index_task_id, vector_id)
        )
    ''')

    # Helper function to check if a column exists
    def column_exists(table_name: str, column_name: str) -> bool:
        c.execute(f"PRAGMA table_info({table_name})")
        columns = [row[1] for row in c.fetchall()]
        return column_name in columns

    # 3. Create knowledge_system_builds table
    c.execute('''
        CREATE TABLE IF NOT EXISTS knowledge_system_builds (
            collection_name TEXT PRIMARY KEY,
            index_version INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at REAL NOT NULL,
            activated_at REAL,
            error TEXT
        )
    ''')

    # 4. Alter knowledge_documents
    if not column_exists('knowledge_documents', 'active_index_version'):
        c.execute('ALTER TABLE knowledge_documents ADD COLUMN active_index_version INTEGER NOT NULL DEFAULT 0')

    # 5. Alter knowledge_index_tasks
    if not column_exists('knowledge_index_tasks', 'attempt_count'):
        c.execute('ALTER TABLE knowledge_index_tasks ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0')
    if not column_exists('knowledge_index_tasks', 'worker_id'):
        c.execute('ALTER TABLE knowledge_index_tasks ADD COLUMN worker_id TEXT')
    if not column_exists('knowledge_index_tasks', 'heartbeat_at'):
        c.execute('ALTER TABLE knowledge_index_tasks ADD COLUMN heartbeat_at REAL')
    if not column_exists('knowledge_index_tasks', 'target_index_version'):
        c.execute('ALTER TABLE knowledge_index_tasks ADD COLUMN target_index_version INTEGER NOT NULL DEFAULT 1')

    # 6. Alter knowledge_chunks
    if not column_exists('knowledge_chunks', 'index_version'):
        c.execute('ALTER TABLE knowledge_chunks ADD COLUMN index_version INTEGER NOT NULL DEFAULT 1')

    # 7. Alter knowledge_index_vectors
    if not column_exists('knowledge_index_vectors', 'index_version'):
        c.execute('ALTER TABLE knowledge_index_vectors ADD COLUMN index_version INTEGER NOT NULL DEFAULT 1')

    # 8. Add Indexes
    c.execute('''
        CREATE INDEX IF NOT EXISTS idx_index_vectors_task_state
        ON knowledge_index_vectors(index_task_id, state)
    ''')

    c.execute('''
        CREATE INDEX IF NOT EXISTS idx_index_tasks_status_heartbeat
        ON knowledge_index_tasks(status, heartbeat_at)
    ''')

    c.execute('''
        CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_document_version
        ON knowledge_chunks(document_id, index_version)
    ''')

    c.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_system_builds_index_version
        ON knowledge_system_builds(index_version)
    ''')

    # 9. Backfills
    # Backfill active_index_version only for documents that have actual chunks
    c.execute("""
        UPDATE knowledge_documents
        SET active_index_version = (
            SELECT MAX(kc.index_version)
            FROM knowledge_chunks kc
            WHERE kc.document_id = knowledge_documents.document_id
        )
        WHERE active_index_version = 0
          AND status IN ('ready', 'reindexing')
          AND EXISTS (
              SELECT 1
              FROM knowledge_chunks kc
              WHERE kc.document_id = knowledge_documents.document_id
          )
    """)

    # Mark ready/reindexing documents without chunks as failed
    c.execute("""
        UPDATE knowledge_documents
        SET status = 'failed',
            error = '迁移时发现文档无有效分块'
        WHERE active_index_version = 0
          AND status IN ('ready', 'reindexing')
          AND NOT EXISTS (
              SELECT 1
              FROM knowledge_chunks kc
              WHERE kc.document_id = knowledge_documents.document_id
          )
    """)

    # 10. Interrupt existing active index tasks during migration
    import time
    now = time.time()
    c.execute("""
        UPDATE knowledge_index_tasks
        SET status = 'interrupted',
            error = '数据库升级后需要重新提交索引任务',
            updated_at = ?
        WHERE status IN ('pending', 'running')
    """, (now,))
    
    c.execute("""
        UPDATE knowledge_documents
        SET status = CASE WHEN active_index_version > 0 THEN 'ready' ELSE 'failed' END,
            error = '原索引任务因数据库升级中断'
        WHERE status IN ('indexing', 'reindexing')
    """)

    conn.commit()
