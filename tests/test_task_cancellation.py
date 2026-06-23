import os
import pytest
import time
import json
from src.runtime.task_store import (
    create_task, request_task_cancel, get_task, update_active_task,
    finish_cancelled_task, complete_task, fail_task, update_task_progress
)

@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    test_db = "data/test_cancellation.db"
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

def test_cancel_blocks_progress_and_resources():
    task_id = create_task("test input")
    
    # Send cancel request
    request_task_cancel(task_id)
    
    # Try to update active task
    saved = update_active_task(
        task_id, 
        progress=50, 
        current_stage="test stage", 
        generated_resources={"test": "data"}
    )
    
    assert saved is False
    
    task = get_task(task_id)
    assert task["progress"] == 0
    assert task["status"] == "cancel_requested"
    assert task["generated_resources"] == {}

def test_cancel_blocks_terminal_completion():
    task_id = create_task("test input")
    request_task_cancel(task_id)
    
    saved = complete_task(task_id, resources={"final": "yes"})
    assert saved is False
    
    task = get_task(task_id)
    assert task["status"] == "cancel_requested"

def test_finish_cancelled_task():
    task_id = create_task("test input")
    request_task_cancel(task_id)
    
    saved = finish_cancelled_task(task_id)
    assert saved is True
    
    task = get_task(task_id)
    assert task["status"] == "cancelled"

def test_cancel_blocks_progress_function():
    task_id = create_task("test input")
    request_task_cancel(task_id)
    
    saved = update_task_progress(task_id, progress=30, current_stage="doing")
    assert saved is False
