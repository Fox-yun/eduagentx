import os
import pytest
import time
from src.runtime.task_store import (
    create_task, request_task_cancel, get_task, recover_tasks_on_startup,
    recover_stale_tasks
)

@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    test_db = "data/test_recovery.db"
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

def test_recover_tasks_on_startup():
    task1 = create_task("test 1")
    task2 = create_task("test 2")
    request_task_cancel(task2)
    
    result = recover_tasks_on_startup()
    assert result["interrupted"] == 1
    assert result["cancelled"] == 1
    
    t1 = get_task(task1)
    t2 = get_task(task2)
    assert t1["status"] == "interrupted"
    assert t2["status"] == "cancelled"

def test_recover_stale_tasks(monkeypatch):
    task_id = create_task("test 1")
    task_cancel_id = create_task("test 2")
    request_task_cancel(task_cancel_id)
    
    # Mock time so task appears stale
    # heartbeat_at is set to "now" when created. We advance time.
    original_time = time.time
    monkeypatch.setattr(time, "time", lambda: original_time() + 600)
    
    # timeout is 300 seconds
    result = recover_stale_tasks(timeout_seconds=300)
    assert result["expired"] == 1
    assert result["cancelled"] == 1
    assert result["total"] == 2
    
    t = get_task(task_id)
    assert t["status"] == "expired"
    
    t_c = get_task(task_cancel_id)
    assert t_c["status"] == "cancelled"
