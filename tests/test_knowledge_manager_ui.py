import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox, QDialog
from PyQt6.QtCore import Qt
from desktop_client.widgets.knowledge_manager import KnowledgeManagerDialog, KnowledgeUploadConfigDialog

class MockApiClient:
    def __init__(self):
        self.base_url = "http://fake"
        
    def get_documents(self, user_id, course_id=None, scope=None, page=1, page_size=20):
        return {
            "items": [],
            "total": 0,
            "page": page,
            "page_size": page_size
        }
        
    def upload_document(self, file_path, user_id, course_id, scope, conversation_id=None):
        return {"document_id": "fake_id", "status": "pending"}
        
    def delete_document(self, document_id, user_id):
        return {"message": "ok"}
        
    def reindex_document(self, document_id, user_id):
        return {"message": "ok"}

@pytest.fixture
def mock_api():
    return MockApiClient()

def test_knowledge_manager_initialization(qtbot, mock_api):
    dialog = KnowledgeManagerDialog(api_client=mock_api, user_id="test_user", conversation_id="conv1")
    qtbot.addWidget(dialog)
    
    assert dialog.windowTitle() == "知识库管理"
    assert dialog.user_id == "test_user"
    assert dialog.table.columnCount() == 7

def test_upload_config_dialog(qtbot):
    dialog = KnowledgeUploadConfigDialog(file_count=3, conversation_id="conv1")
    qtbot.addWidget(dialog)
    
    # Check default selection
    assert dialog.scope_combo.currentData() == "personal"
    assert dialog.course_combo.currentData() == ""
    
    # Check session is enabled
    assert dialog.scope_combo.model().item(1).isEnabled() == True
    
def test_upload_config_dialog_no_session(qtbot):
    dialog = KnowledgeUploadConfigDialog(file_count=3, conversation_id=None)
    qtbot.addWidget(dialog)
    
    # Check session is disabled
    assert dialog.scope_combo.model().item(1).isEnabled() == False

def test_refresh_generation_lock(qtbot, mock_api):
    dialog = KnowledgeManagerDialog(api_client=mock_api, user_id="test_user", conversation_id="conv1")
    qtbot.addWidget(dialog)
    
    initial_gen = dialog.refresh_generation
    dialog.refresh_in_progress = False
    dialog.refresh_documents()
    assert dialog.refresh_generation == initial_gen + 1
    assert dialog.refresh_in_progress == True
    
    # Calling refresh again should be blocked by the lock
    dialog.refresh_documents()
    assert dialog.refresh_generation == initial_gen + 1
    
    # Manually unlock and loaded logic
    dialog.on_documents_loaded({"items": [], "total": 0}, initial_gen + 1)
    # the flag is reset in finished signal, skipped in mock test
