import os
import pytest
from src.runtime.task_store import (
    create_task, update_task, get_task, fail_task, expire_task, complete_task
)

@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    test_db = "data/test_transitions.db"
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

def test_update_task_forbids_status_modification():
    task_id = create_task("test input")
    
    with pytest.raises(ValueError, match="状态字段必须通过专用转换函数修改"):
        update_task(task_id, status="failed")

def test_fail_task_transition():
    task_id = create_task("test input")
    saved = fail_task(task_id, stage="error stage", error="test error")
    assert saved is True
    
    task = get_task(task_id)
    assert task["status"] == "failed"
    assert task["error"] == "test error"

def test_expire_task_transition():
    task_id = create_task("test input")
    saved = expire_task(task_id, reason="time out")
    assert saved is True
    
    task = get_task(task_id)
    assert task["status"] == "expired"
    assert task["error"] == "time out"

def test_transitions_only_from_active_states():
    task_id = create_task("test input")
    fail_task(task_id, stage="first", error="1")
    
    # Try to expire a failed task
    saved = expire_task(task_id, reason="time out")
    assert saved is False
    
    # Try to complete a failed task
    saved = complete_task(task_id, resources={"a": "b"})
    assert saved is False
