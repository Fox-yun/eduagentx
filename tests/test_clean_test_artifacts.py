import os
import pytest
import sqlite3
from pathlib import Path
from scripts.clean_test_artifacts import clean_test_artifacts, safe_delete_path

def test_safe_delete_path_safety_check(tmp_path):
    # Try deleting a path outside project boundaries (e.g. /etc or tmp_path which is outside workspace data directory)
    outside_path = Path("/tmp/unsafe_test_path")
    if not outside_path.exists():
        try:
            outside_path.touch()
        except:
            pass
            
    with pytest.raises(RuntimeError) as excinfo:
        safe_delete_path(outside_path)
    assert "safety boundaries" in str(excinfo.value)
    
    # Try deleting a path under the PROJECT_ROOT/data/ directory (should be allowed)
    from scripts.clean_test_artifacts import DATA_DIR
    inside_path = DATA_DIR / "test_dummy_safety.txt"
    # Ensure directory exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    inside_path.touch()
    assert inside_path.exists()
    
    # Run safe_delete_path (should succeed)
    safe_delete_path(inside_path)
    assert not inside_path.exists()

def test_clean_test_artifacts_execution(tmp_path):
    db_path = os.path.join(tmp_path, "clean_test.db")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # Create tasks table
    c.execute("""
        CREATE TABLE tasks (
            task_id TEXT PRIMARY KEY,
            user_id TEXT
        )
    """)
    # Insert test_user matching LIKE test\_% ESCAPE '\'
    c.execute("INSERT INTO tasks VALUES ('task_test_1', 'test_user1')")
    c.execute("INSERT INTO tasks VALUES ('task_test_2', 'test_user_two')")
    # Insert non-matching records (e.g. testimonial_001, testing_user)
    c.execute("INSERT INTO tasks VALUES ('task_ok_1', 'testimonial_001')")
    c.execute("INSERT INTO tasks VALUES ('task_ok_2', 'testing_user')")
    c.execute("INSERT INTO tasks VALUES ('task_ok_3', 'normal_user')")
    conn.commit()
    conn.close()
    
    # Run cleanup in dry-run
    clean_test_artifacts(db_path, execute=False)
    # Check that records are still there
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM tasks")
    assert c.fetchone()[0] == 5
    
    # Run cleanup in execute mode
    conn.close()
    clean_test_artifacts(db_path, execute=True)
    
    # Verify records in tasks
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT task_id FROM tasks")
    tasks = [r[0] for r in c.fetchall()]
    assert "task_test_1" not in tasks
    assert "task_test_2" not in tasks
    assert "task_ok_1" in tasks
    assert "task_ok_2" in tasks
    assert "task_ok_3" in tasks
    conn.close()
