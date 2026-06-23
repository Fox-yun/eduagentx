import sqlite3
import json
import uuid
import time
import os
from typing import Dict, Any

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
if not os.path.exists(DB_DIR):
    os.makedirs(DB_DIR)
DB_PATH = os.environ.get("SQLITE_DB_PATH", os.path.join(DB_DIR, "tasks.db"))

def get_connection():
    db_path = os.environ.get("SQLITE_DB_PATH", os.path.join(DB_DIR, "tasks.db"))
    # 增加 timeout 到 30 秒以应对多线程并发写入时的 database is locked 错误
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
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
    
    # Existing dynamic alterations
    for col in ['user_id', 'conversation_id', 'conversation_summary', 'request_id']:
        try:
            c.execute(f'ALTER TABLE tasks ADD COLUMN {col} TEXT')
        except sqlite3.OperationalError:
            pass

    # Phase 1 new dynamic alterations
    for col_def in [
        'started_at REAL',
        'completed_at REAL',
        'heartbeat_at REAL',
        'cancel_requested_at REAL',
        'worker_id TEXT',
        "retry_count INTEGER DEFAULT 0",
        "requested_resources TEXT DEFAULT '[]'",
        "schema_version TEXT DEFAULT '1.0'"
    ]:
        try:
            c.execute(f'ALTER TABLE tasks ADD COLUMN {col_def}')
        except sqlite3.OperationalError:
            pass

    # Create task_resources table
    c.execute('''
        CREATE TABLE IF NOT EXISTS task_resources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            status TEXT NOT NULL,
            progress INTEGER DEFAULT 0,
            content TEXT,
            error TEXT,
            started_at REAL,
            completed_at REAL,
            retry_count INTEGER DEFAULT 0,
            UNIQUE(task_id, resource_type)
        )
    ''')

    # Create knowledge_documents table
    c.execute('''
        CREATE TABLE IF NOT EXISTS knowledge_documents (
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
    
    # Create unique index for user_id and sha256
    c.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_knowledge_document_user_hash 
        ON knowledge_documents(user_id, sha256) 
        WHERE status != 'deleted'
    ''')

    # Create knowledge_index_tasks table
    c.execute('''
        CREATE TABLE IF NOT EXISTS knowledge_index_tasks (
            index_task_id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            status TEXT NOT NULL,
            progress INTEGER DEFAULT 0,
            current_stage TEXT,
            error TEXT,
            retry_count INTEGER DEFAULT 0,
            heartbeat_at REAL,
            worker_id TEXT,
            started_at REAL,
            completed_at REAL,
            cancel_requested_at REAL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            target_index_version INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY(document_id) REFERENCES knowledge_documents(document_id)
        )
    ''')

    # Create knowledge_chunks table
    c.execute('''
        CREATE TABLE IF NOT EXISTS knowledge_chunks (
            chunk_id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            vector_id TEXT NOT NULL,
            page_number INTEGER,
            chunk_index INTEGER NOT NULL,
            content_hash TEXT,
            index_version INTEGER NOT NULL DEFAULT 1,
            created_at REAL NOT NULL,
            FOREIGN KEY(document_id) REFERENCES knowledge_documents(document_id)
        )
    ''')

    # Create knowledge_system_builds table
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

    from src.db.migrations import run_migrations
    run_migrations(conn)

    conn.commit()
    conn.close()

init_db()
