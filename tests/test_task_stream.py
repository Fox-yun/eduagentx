import os
import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from src.api.server import app
from src.runtime.task_store import create_task, request_task_cancel, get_task, update_task_progress

@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    test_db = "data/test_stream.db"
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

@pytest.mark.asyncio
async def test_stream_terminal_state():
    task_id = create_task("test input")
    request_task_cancel(task_id)
    # The stream should immediately yield cancel_requested (because it's not terminal) and then we need to wait? Wait, the stream pushes updates. Let's finish the task to cancelled.
    from src.runtime.task_store import finish_cancelled_task
    finish_cancelled_task(task_id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with client.stream("GET", f"/api/task/{task_id}/stream") as response:
            events = []
            async for chunk in response.aiter_text():
                events.append(chunk)
            
            assert len(events) > 0
            assert "cancelled" in "".join(events)
            # The stream should terminate automatically.
