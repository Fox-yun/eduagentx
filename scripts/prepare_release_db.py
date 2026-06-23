import os
import sys
import argparse
import sqlite3

def prepare_release_db(db_path: str, mode: str):
    if mode == "empty":
        if os.path.exists(db_path):
            os.remove(db_path)
            print(f"Removed existing database at {db_path}")
        
        # Initialize schema
        os.environ["SQLITE_DB_PATH"] = db_path
        from src.db.database import init_db
        init_db()
        print("Created empty database schema.")
        return

    if mode == "clear-active":
        if not os.path.exists(db_path):
            print(f"Database not found at {db_path}, nothing to clear.")
            return
            
        import time
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("BEGIN IMMEDIATE")
        
        # 1. Update chat tasks
        cursor.execute(
            """
            UPDATE tasks
            SET status = CASE
                WHEN status IN ('pending', 'running') THEN 'interrupted'
                WHEN status = 'cancel_requested' THEN 'cancelled'
                ELSE status
            END,
            current_stage = CASE
                WHEN status IN ('pending', 'running') THEN '任务被中断'
                WHEN status = 'cancel_requested' THEN '任务已取消'
                ELSE current_stage
            END,
            updated_at = ?
            WHERE status IN ('pending', 'running', 'cancel_requested')
            """,
            (time.time(),)
        )
        task_updates = cursor.rowcount
        
        # 2. Update index tasks
        cursor.execute(
            """
            UPDATE knowledge_index_tasks
            SET status = 'interrupted',
                error = '发布准备，任务被中断',
                updated_at = ?
            WHERE status IN ('pending', 'running')
            """,
            (time.time(),)
        )
        index_task_updates = cursor.rowcount
        
        # 3. Update documents
        cursor.execute(
            """
            UPDATE knowledge_documents
            SET status = CASE
                WHEN status = 'reindexing' AND active_index_version > 0 THEN 'ready'
                WHEN status = 'reindexing' AND active_index_version = 0 THEN 'failed'
                WHEN status = 'indexing' THEN 'failed'
                WHEN status = 'deleting' THEN 'delete_failed'
                ELSE status
            END,
            error = CASE
                WHEN status = 'reindexing' AND active_index_version > 0 THEN NULL
                WHEN status = 'reindexing' AND active_index_version = 0 THEN '发布准备，重新索引中断'
                WHEN status = 'indexing' THEN '发布准备，索引中断'
                WHEN status = 'deleting' THEN '发布准备，删除中断'
                ELSE error
            END,
            updated_at = ?
            WHERE status IN ('indexing', 'reindexing', 'deleting')
            """,
            (time.time(),)
        )
        doc_updates = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        print(f"Transitioned {task_updates} chat tasks, {index_task_updates} index tasks, and {doc_updates} documents to terminal states in {db_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prepare the SQLite database for release.")
    parser.add_argument(
        "--db-path", 
        type=str, 
        default="data/tasks.db",
        help="Path to the SQLite database file"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--clear-active",
        action="store_const",
        dest="mode",
        const="clear-active",
        help="Delete all pending, running, and cancel_requested tasks"
    )
    group.add_argument(
        "--empty",
        action="store_const",
        dest="mode",
        const="empty",
        help="Create a completely empty database, destroying existing data"
    )
    
    args = parser.parse_args()
    
    # Ensure src is in python path
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    
    prepare_release_db(args.db_path, args.mode)
