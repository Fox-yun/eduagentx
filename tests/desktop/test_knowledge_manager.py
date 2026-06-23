import pytest
from desktop_client.api_client import EduAgentApiClient, ApiClientError
from desktop_client.widgets.knowledge_manager import KnowledgeManagerDialog
from desktop_client.workers.knowledge_workers import ApiCallWorker
from PyQt6.QtWidgets import QApplication

class MockApiClient(EduAgentApiClient):
    def __init__(self):
        super().__init__("http://mock")
        self.upload_called = False
        self.get_docs_called = False
        self.delete_called = False
        self.reindex_called = False
        
    def upload_document(self, file_path, user_id, course_id=None, scope='personal', conversation_id=None):
        self.upload_called = True
        return {"status": "ok"}
        
    def get_documents(self, user_id=None, course_id=None, scope=None, status=None, page=1, page_size=100):
        self.get_docs_called = True
        return {"items": [], "total": 0}
        
    def delete_document(self, document_id, user_id):
        self.delete_called = True
        return {"status": "deleted"}
        
    def reindex_document(self, document_id, user_id):
        self.reindex_called = True
        return {"status": "reindexed"}

def test_api_call_worker(qtbot):
    def success_callback():
        return "success"
        
    worker = ApiCallWorker(success_callback)
    
    with qtbot.waitSignal(worker.succeeded, timeout=1000) as blocker:
        worker.start()
        
    assert blocker.args[0] == "success"

def test_api_call_worker_fail(qtbot):
    def fail_callback():
        raise ValueError("error")
        
    worker = ApiCallWorker(fail_callback)
    
    with qtbot.waitSignal(worker.failed, timeout=1000) as blocker:
        worker.start()
        
    assert "error" in blocker.args[0]

def test_knowledge_manager_init(qtbot):
    # This ensures the dialog can be constructed and initialized without errors
    mock_client = MockApiClient()
    dialog = KnowledgeManagerDialog(api_client=mock_client, user_id="test_user")
    qtbot.addWidget(dialog)
    
    assert dialog.windowTitle() == "知识库管理"
    assert dialog.table.columnCount() == 7
    assert dialog.course_combo.count() >= 1
    assert dialog.scope_combo.count() >= 1
    
    # Wait for the initial load to finish (mock is fast)
    qtbot.wait(100)
    assert mock_client.get_docs_called == True
