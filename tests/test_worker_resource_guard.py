import os
import pytest
from src.runtime.task_store import create_task, request_task_cancel, TaskStateConflictError
from src.agents.diagnostic_group import extract_profile_with_llm

@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    test_db = "data/test_worker.db"
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

def test_extract_profile_aborts_if_cancelled(monkeypatch):
    task_id = create_task("test input")
    
    # Mock LLM call to simulate delay
    def mock_invoke(*args, **kwargs):
        request_task_cancel(task_id) # Simulate user cancelling during LLM call
        class MockResult:
            def model_dump(self, *args, **kwargs):
                return {"preference": "test"}
        return MockResult()
        
    monkeypatch.setattr("src.agents.diagnostic_group.invoke_structured", mock_invoke)
    
    from src.runtime.task_store import TaskCancelledError
    
    with pytest.raises(TaskCancelledError):
        extract_profile_with_llm(task_id, {}, "test message", 0)
