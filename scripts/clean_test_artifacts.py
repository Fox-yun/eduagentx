import os
import sys
import argparse
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = (PROJECT_ROOT / "data").resolve()

def table_exists(cursor, table_name: str) -> bool:
    cursor.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        """,
        (table_name,),
    )
    return cursor.fetchone() is not None

def safe_delete_path(path: Path):
    path = path.resolve()
    
    # Safety Check: Path must be under DATA_DIR or match root-level whitelist
    is_under_data = DATA_DIR in path.parents or path == DATA_DIR
    is_whitelisted_root = path in [
        PROJECT_ROOT / ".coverage",
        PROJECT_ROOT / ".pytest_cache",
        PROJECT_ROOT / "htmlcov"
    ] or (PROJECT_ROOT in path.parents and path.name == "__pycache__")
    
    if not (is_under_data or is_whitelisted_root):
        raise RuntimeError(f"Refusing to delete path outside safety boundaries: {path}")
        
    if path.is_file() or path.is_symlink():
        os.remove(path)
        print(f"Deleted file: {path}")
    elif path.is_dir():
        import shutil
        shutil.rmtree(path)
        print(f"Deleted directory: {path}")

def find_files_to_clean():
    to_delete = []
    
    # 1. Root files/folders
    root_items = [".coverage", ".pytest_cache", "htmlcov"]
    for item in root_items:
        path = PROJECT_ROOT / item
        if path.exists():
            to_delete.append(path)
            
    # 2. data/test_*.db and test directories
    if DATA_DIR.exists():
        for filename in os.listdir(DATA_DIR):
            path = DATA_DIR / filename
            if filename.startswith("test_") and filename.endswith(".db"):
                to_delete.append(path)
            elif filename.startswith("test_chroma") or filename.startswith("test_upload"):
                to_delete.append(path)
                
    # 3. Recursive __pycache__ (excluding virtualenv)
    for root, dirs, files in os.walk(PROJECT_ROOT):
        if ".venv" in root or ".pytest_cache" in root or ".git" in root:
            continue
        for d in dirs:
            if d == "__pycache__":
                to_delete.append(Path(root) / d)
                
    return list(set(to_delete))

def clean_test_artifacts(db_path: str, execute: bool):
    print(f"=== Cleaning Test Artifacts ===")
    
    # Find database records to delete
    test_docs = []
    test_tasks = []
    
    db_exists = os.path.exists(db_path)
    if db_exists:
        print(f"Scanning database {db_path} for records...")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            if table_exists(cursor, "knowledge_documents"):
                cursor.execute(
                    "SELECT document_id FROM knowledge_documents WHERE user_id LIKE 'test\\_%' ESCAPE '\\'"
                )
                test_docs = [row["document_id"] for row in cursor.fetchall()]
                
            if table_exists(cursor, "tasks"):
                cursor.execute(
                    "SELECT task_id FROM tasks WHERE user_id LIKE 'test\\_%' ESCAPE '\\'"
                )
                test_tasks = [row["task_id"] for row in cursor.fetchall()]
        except Exception as e:
            print(f"Database scan failed: {e}")
        finally:
            conn.close()
            
    files_to_clean = find_files_to_clean()
    
    print(f"\nFound {len(test_docs)} test documents in DB.")
    print(f"Found {len(test_tasks)} test chat tasks in DB.")
    print(f"Found {len(files_to_clean)} test files/directories to delete on disk.")
    
    if not execute:
        print("\n--- Plan (DRY RUN) ---")
        if test_docs:
            print(f"DB: Will delete {len(test_docs)} test documents and related chunks/tasks.")
        if test_tasks:
            print(f"DB: Will delete {len(test_tasks)} test chat tasks.")
        for f in files_to_clean:
            print(f"Disk: Will delete {f}")
        print("\nTo execute actual deletion, run with the --execute flag.")
        return
        
    # Execute deletion
    if db_exists and (test_docs or test_tasks):
        print("\nExecuting database cleanup...")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        
        try:
            if test_docs:
                placeholders = ",".join(["?"] * len(test_docs))
                if table_exists(cursor, "knowledge_chunks"):
                    cursor.execute(f"DELETE FROM knowledge_chunks WHERE document_id IN ({placeholders})", test_docs)
                if table_exists(cursor, "knowledge_index_vectors"):
                    cursor.execute(f"DELETE FROM knowledge_index_vectors WHERE document_id IN ({placeholders})", test_docs)
                if table_exists(cursor, "knowledge_index_tasks"):
                    cursor.execute(f"DELETE FROM knowledge_index_tasks WHERE document_id IN ({placeholders})", test_docs)
                if table_exists(cursor, "knowledge_documents"):
                    cursor.execute(f"DELETE FROM knowledge_documents WHERE document_id IN ({placeholders})", test_docs)
                print(f"Deleted test documents records.")
                
            if test_tasks:
                placeholders = ",".join(["?"] * len(test_tasks))
                if table_exists(cursor, "task_messages"):
                    cursor.execute(f"DELETE FROM task_messages WHERE task_id IN ({placeholders})", test_tasks)
                if table_exists(cursor, "tasks"):
                    cursor.execute(f"DELETE FROM tasks WHERE task_id IN ({placeholders})", test_tasks)
                print(f"Deleted test chat tasks records.")
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"Failed to execute database cleanup: {e}")
        finally:
            conn.close()
            
    if files_to_clean:
        print("\nExecuting disk files cleanup...")
        for f in files_to_clean:
            try:
                safe_delete_path(f)
            except Exception as e:
                print(f"Failed to delete {f}: {e}")
                
    print("\nCleanup completed.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean test artifacts from database and disk")
    parser.add_argument(
        "--db-path", 
        type=str, 
        default="data/tasks.db",
        help="Path to the SQLite database file"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually perform the deletion. Without this flag, it does a dry run."
    )
    args = parser.parse_args()
    
    clean_test_artifacts(args.db_path, args.execute)
