import pytest
import time
from src.runtime.task_store import (
    create_task, request_task_cancel, TaskCancelledError,
    TaskStateConflictError, get_task
)
import os
os.environ["OPENAI_API_KEY"] = "test_key"

from src.agents.diagnostic_group import (
    save_diagnostic_progress, profiler_node, diagnoser_node, extract_profile_with_llm
)

@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    test_db = "data/test_diag_guard.db"
    import os
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

def test_save_diagnostic_progress_raises_on_cancelled():
    task_id = create_task("test input")
    request_task_cancel(task_id)
    
    with pytest.raises((TaskStateConflictError, TaskCancelledError)):
        save_diagnostic_progress(
            {"task_id": task_id},
            progress=50,
            stage="test stage"
        )

def test_profiler_fast_path_cancel():
    task_id = create_task("我希望能快速学会这个，越简单越好。")
    state = {"task_id": task_id, "messages": ["我希望能快速学会这个，越简单越好。"], "student_profile": {}}
    
    # We cancel it
    request_task_cancel(task_id)
    
    # Since it's cancelled, when profiler tries to update progress in the fast path, it will raise TaskStateConflictError (from save_diagnostic_progress) or TaskCancelledError (from check_cancellation_and_deadline)
    with pytest.raises((TaskCancelledError, TaskStateConflictError)):
        profiler_node(state)
        
    t = get_task(task_id)
    # Shouldn't have updated the trace since it failed at check or save
    assert "agent_trace" not in t or "本地更新临时偏好或画像" not in str(t["agent_trace"])

def test_diagnoser_retrieval_cancel(monkeypatch):
    task_id = create_task("test retrieval input")
    state = {"task_id": task_id, "messages": ["test input"], "mode": "快速模式"}
    
    def mock_retrieve_authorized_documents(*args, **kwargs):
        # simulate cancellation mid-retrieval
        request_task_cancel(task_id)
        class MockDoc:
            page_content = "content"
            metadata = {"source": "test.pdf"}
        return [MockDoc()]
        
    monkeypatch.setattr("src.agents.diagnostic_group.retrieve_authorized_documents", mock_retrieve_authorized_documents)
    
    with pytest.raises(TaskCancelledError):
        diagnoser_node(state)
        
    t = get_task(task_id)
    assert t["status"] == "cancel_requested"
    assert "retrieved_sources" not in str(t.get("retrieved_sources", ""))

def test_diagnoser_retrieval_exception_when_cancelled(monkeypatch):
    task_id = create_task("test retrieval exception")
    state = {"task_id": task_id, "messages": ["test input"], "mode": "快速模式"}
    
    def mock_retrieve_authorized_documents(*args, **kwargs):
        request_task_cancel(task_id)
        raise RuntimeError("Database connection lost")
        
    monkeypatch.setattr("src.agents.diagnostic_group.retrieve_authorized_documents", mock_retrieve_authorized_documents)
    
    with pytest.raises(TaskCancelledError):
        diagnoser_node(state)
