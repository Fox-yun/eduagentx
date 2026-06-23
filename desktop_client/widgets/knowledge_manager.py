import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
    QMessageBox, QComboBox, QLineEdit, QWidget
)
from PyQt6.QtCore import Qt, QTimer
from desktop_client.workers.knowledge_workers import ApiCallWorker
from desktop_client.api_client import EduAgentApiClient

DOCUMENT_STATUS_TEXT = {
    "uploaded": "已上传",
    "queued": "等待索引",
    "pending": "等待索引", # backend initial status
    "parsing": "正在解析",
    "chunking": "正在分块",
    "indexing": "正在建立索引",
    "running": "正在建立索引", # backend index task status
    "ready": "已就绪",
    "completed": "已就绪",
    "failed": "处理失败",
    "deleting": "正在删除",
    "deleted": "已删除",
    "reindexing": "正在重新索引",
    "delete_failed": "删除失败",
    "uploading": "正在上传"
}

SCOPE_TEXT = {
    "personal": "个人资料库",
    "session": "当前会话",
    "system": "系统资料"
}

class KnowledgeUploadConfigDialog(QDialog):
    def __init__(self, file_count, conversation_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle("上传资料配置")
        self.resize(350, 200)
        self.conversation_id = conversation_id
        self.init_ui(file_count)

    def init_ui(self, file_count):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"已选择 {file_count} 个文件，请配置属性："))
        
        self.course_combo = QComboBox()
        self.course_combo.addItem("无（全局可用）", "")
        self.course_combo.addItem("人工智能导论", "ai_intro")
        
        self.scope_combo = QComboBox()
        self.scope_combo.addItem("个人资料库", "personal")
        self.scope_combo.addItem("当前会话", "session")
        if not self.conversation_id:
            self.scope_combo.model().item(1).setEnabled(False)
            self.scope_combo.setToolTip("当前没有激活的会话，无法上传至当前会话")
            
        layout.addWidget(QLabel("关联课程:"))
        layout.addWidget(self.course_combo)
        layout.addWidget(QLabel("资料范围:"))
        layout.addWidget(self.scope_combo)
        
        btn_layout = QHBoxLayout()
        self.upload_btn = QPushButton("确定上传")
        self.upload_btn.clicked.connect(self.accept)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.upload_btn)
        layout.addLayout(btn_layout)

class KnowledgeManagerDialog(QDialog):
    def __init__(self, api_client: EduAgentApiClient, user_id: str, conversation_id: str = None, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self.user_id = user_id
        self.conversation_id = conversation_id
        
        self.setWindowTitle("知识库管理")
        self.resize(800, 500)
        
        self.workers = set() # use set to keep references and allow easy removal
        self.pending_uploads = {} # local_upload_id -> info dict
        self.refresh_generation = 0
        self.refresh_in_progress = False
        self.refresh_pending = False
        self.is_closing = False
        
        self.init_ui()
        
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(2000)
        self.poll_timer.timeout.connect(self.refresh_documents)
        
        self.refresh_documents()
        
    def register_worker(self, worker):
        self.workers.add(worker)
        
        def cleanup():
            self.workers.discard(worker)
            worker.deleteLater()
            
        worker.finished.connect(cleanup)
        worker.start()

    def can_update_ui(self) -> bool:
        return not self.is_closing

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Header controls
        header_layout = QHBoxLayout()
        
        self.upload_btn = QPushButton("上传文件")
        self.upload_btn.clicked.connect(self.on_upload_clicked)
        
        self.course_combo = QComboBox()
        self.course_combo.addItem("全部课程", "__all__")
        self.course_combo.addItem("无（全局资料）", "__none__")
        self.course_combo.addItem("人工智能导论", "ai_intro")
        self.course_combo.currentTextChanged.connect(self.on_filter_changed)
        
        self.scope_combo = QComboBox()
        self.scope_combo.addItem("全部范围", "")
        self.scope_combo.addItem("个人资料库", "personal")
        self.scope_combo.addItem("当前会话", "session")
        self.scope_combo.addItem("系统资料", "system")
        self.scope_combo.currentTextChanged.connect(self.on_filter_changed)
        
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("搜索...")
        self.search_box.textChanged.connect(self.render_table)
        
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.refresh_documents)
        
        header_layout.addWidget(self.upload_btn)
        header_layout.addWidget(QLabel("课程:"))
        header_layout.addWidget(self.course_combo)
        header_layout.addWidget(QLabel("范围:"))
        header_layout.addWidget(self.scope_combo)
        header_layout.addWidget(self.search_box)
        header_layout.addStretch()
        header_layout.addWidget(self.refresh_btn)
        
        layout.addLayout(header_layout)
        
        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "名称", "课程", "范围", "状态/进度", "大小", "分块", "操作"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)
        
        # Footer
        self.status_label = QLabel("加载中...")
        layout.addWidget(self.status_label)

    def on_upload_clicked(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择课程资料",
            "",
            "支持的资料 (*.pdf *.txt *.md)"
        )
        if not files:
            return
            
        if len(files) > 5:
            QMessageBox.warning(self, "限制", "单次最多上传 5 个文件")
            files = files[:5]
            
        dialog = KnowledgeUploadConfigDialog(len(files), self.conversation_id, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            course_id = dialog.course_combo.currentData()
            scope = dialog.scope_combo.currentData()
            self.upload_files(files, course_id, scope)

    def upload_files(self, files, course_id, scope):
        import uuid
        for fpath in files:
            local_id = f"temp_{uuid.uuid4().hex[:8]}"
            self.pending_uploads[local_id] = {
                "display_name": os.path.basename(fpath),
                "course_id": course_id,
                "scope": scope,
                "status": "uploading",
                "file_size": os.path.getsize(fpath)
            }
            
            worker = ApiCallWorker(
                self.api_client.upload_document,
                fpath, self.user_id, course_id, scope, self.conversation_id
            )
            # Use default arguments to capture loop variables correctly
            worker.succeeded.connect(lambda res, lid=local_id: self.on_upload_success(res, lid))
            worker.failed.connect(lambda err, lid=local_id, fname=os.path.basename(fpath): self.on_upload_error(lid, fname, err))
            self.register_worker(worker)
            
        self.render_table()

    def on_upload_success(self, result, local_id):
        if not self.can_update_ui():
            return
        if local_id in self.pending_uploads:
            del self.pending_uploads[local_id]
        self.refresh_documents()
        
    def on_upload_error(self, local_id, fname, err):
        if not self.can_update_ui():
            return
        if local_id in self.pending_uploads:
            self.pending_uploads[local_id]["status"] = "failed"
            self.pending_uploads[local_id]["error"] = f"上传失败: {err}"
        QMessageBox.warning(self, "上传失败", f"文件 {fname} 上传失败:\n{err}")
        self.render_table()

    def on_filter_changed(self):
        self.refresh_generation += 1
        self.refresh_documents()

    def refresh_documents(self):
        if self.refresh_in_progress:
            self.refresh_pending = True
            return
            
        self.refresh_generation += 1
        gen = self.refresh_generation
        self.refresh_in_progress = True
        self.refresh_pending = False
        
        course_id = self.course_combo.currentData()
        if course_id == "__all__":
            course_id = None
            
        scope = self.scope_combo.currentData()
        
        worker = ApiCallWorker(
            self.api_client.get_documents,
            user_id=self.user_id,
            course_id=course_id,
            scope=scope,
            page=1,
            page_size=100
        )
        worker.succeeded.connect(lambda res: self.on_documents_loaded(res, gen))
        worker.failed.connect(lambda err: self.on_documents_load_error(err, gen))
        
        self.register_worker(worker)

    def finish_refresh(self):
        self.refresh_in_progress = False
        if self.is_closing:
            self.refresh_pending = False
            return
            
        if self.refresh_pending:
            self.refresh_pending = False
            QTimer.singleShot(0, self.refresh_documents)

    def on_documents_loaded(self, result, gen):
        try:
            if not self.can_update_ui():
                return
            if gen != self.refresh_generation:
                return
            
            items = result.get("items", [])
            total = result.get("total", 0)
            
            self.backend_items = items
            self.backend_total = total
            self.render_table()
        finally:
            self.finish_refresh()

    def on_documents_load_error(self, err, gen):
        try:
            if not self.can_update_ui():
                return
            if gen != self.refresh_generation:
                return
            self.status_label.setText("加载失败")
            self.poll_timer.stop()
        finally:
            self.finish_refresh()

    def render_table(self):
        self.table.setRowCount(0)
        active_count = 0
        search_text = self.search_box.text().lower()
        
        items = getattr(self, "backend_items", [])
        total = getattr(self, "backend_total", 0)
        
        rendered_count = 0
        
        # Render backend items
        for doc in items:
            status = doc.get("status")
            if status in ["pending", "indexing", "queued", "parsing", "chunking", "reindexing", "deleting"]:
                active_count += 1
                
            if search_text and search_text not in doc.get("display_name", "").lower():
                continue
                
            self.add_document_row(doc)
            rendered_count += 1
            
        # Render pending uploads
        for lid, info in self.pending_uploads.items():
            if info["status"] == "uploading":
                active_count += 1
                
            if search_text and search_text not in info.get("display_name", "").lower():
                continue
                
            info["document_id"] = lid
            self.add_document_row(info, is_pending=True)
            rendered_count += 1
            
        self.status_label.setText(f"共 {total + len(self.pending_uploads)} 份资料 (显示 {rendered_count} 份)    正在处理 {active_count} 份")
        
        if active_count > 0:
            if not self.poll_timer.isActive():
                self.poll_timer.start()
        else:
            self.poll_timer.stop()

    def format_size(self, size_bytes):
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"

    def add_document_row(self, doc, is_pending=False):
        row = self.table.rowCount()
        self.table.insertRow(row)
        
        doc_id = doc.get("document_id")
        
        name_item = QTableWidgetItem(doc.get("display_name", ""))
        name_item.setData(Qt.ItemDataRole.UserRole, doc_id)
        self.table.setItem(row, 0, name_item)
        
        self.table.setItem(row, 1, QTableWidgetItem(doc.get("course_id") or "无"))
        scope = doc.get("scope", "personal")
        self.table.setItem(row, 2, QTableWidgetItem(SCOPE_TEXT.get(scope, scope)))
        
        status = doc.get("status")
        
        if is_pending and status == "uploading":
            self.table.setItem(row, 3, QTableWidgetItem("正在上传..."))
        else:
            status_text = DOCUMENT_STATUS_TEXT.get(status, status)
            
            # Show progress bar if active indexing task
            index_status = doc.get("index_status")
            if status in ["pending", "indexing", "queued", "parsing", "chunking", "reindexing"] and index_status in ["running", "pending"]:
                progress_widget = QWidget()
                progress_layout = QVBoxLayout(progress_widget)
                progress_layout.setContentsMargins(2, 2, 2, 2)
                progress_layout.setSpacing(2)
                
                from PyQt6.QtWidgets import QProgressBar
                progress_bar = QProgressBar()
                progress_bar.setRange(0, 100)
                progress_bar.setValue(doc.get("index_progress", 0))
                progress_bar.setFixedHeight(12)
                
                stage_label = QLabel(f"{status_text} - {doc.get('index_stage') or '正在处理'}")
                stage_label.setStyleSheet("font-size: 10px; color: gray;")
                
                progress_layout.addWidget(progress_bar)
                progress_layout.addWidget(stage_label)
                self.table.setCellWidget(row, 3, progress_widget)
            else:
                self.table.setItem(row, 3, QTableWidgetItem(status_text))
        
        self.table.setItem(row, 4, QTableWidgetItem(self.format_size(doc.get("file_size", 0))))
        
        chunks = doc.get("chunk_count", 0)
        pages = doc.get("page_count", 0)
        if is_pending and status == "uploading":
            self.table.setItem(row, 5, QTableWidgetItem("-"))
        else:
            self.table.setItem(row, 5, QTableWidgetItem(f"{pages}页 / {chunks}块"))
        
        # Actions
        action_widget = QWidget()
        action_layout = QHBoxLayout(action_widget)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(5)
        
        if is_pending:
            if status == "failed":
                remove_btn = QPushButton("移除")
                remove_btn.clicked.connect(lambda _, lid=doc_id: self.remove_pending_upload(lid))
                action_layout.addWidget(remove_btn)
        else:
            if scope == "system":
                # Visual protection for system documents
                info_label = QLabel("系统文档")
                info_label.setStyleSheet("color: gray;")
                action_layout.addWidget(info_label)
            else:
                if status == "failed" or status == "delete_failed":
                    err_btn = QPushButton("查看错误")
                    err_btn.clicked.connect(lambda _, d=doc: self.show_error(d))
                    action_layout.addWidget(err_btn)
                    
                    reindex_btn = QPushButton("重新索引")
                    reindex_btn.clicked.connect(lambda _, d=doc_id: self.reindex_document(d))
                    action_layout.addWidget(reindex_btn)
                    
                del_btn = QPushButton("删除")
                if status in ["pending", "indexing", "queued", "parsing", "chunking", "reindexing", "deleting"]:
                    del_btn.setEnabled(False)
                del_btn.clicked.connect(lambda _, d=doc_id, n=doc.get("display_name"): self.delete_document(d, n))
                action_layout.addWidget(del_btn)
        
        self.table.setCellWidget(row, 6, action_widget)

    def remove_pending_upload(self, local_id):
        if local_id in self.pending_uploads:
            del self.pending_uploads[local_id]
        self.render_table()

    def show_error(self, doc):
        QMessageBox.warning(self, "资料处理失败", doc.get("error") or "未知错误")

    def reindex_document(self, doc_id):
        worker = ApiCallWorker(self.api_client.reindex_document, doc_id, self.user_id)
        worker.succeeded.connect(lambda _: self.can_update_ui() and self.refresh_documents())
        worker.failed.connect(lambda err: self.can_update_ui() and QMessageBox.warning(self, "重试失败", f"无法重新索引: {err}"))
        self.register_worker(worker)

    def delete_document(self, doc_id, name):
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除资料“{name}”吗？\n删除后该资料将不再参与知识检索。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            worker = ApiCallWorker(self.api_client.delete_document, doc_id, self.user_id)
            worker.succeeded.connect(lambda _: self.can_update_ui() and self.refresh_documents())
            worker.failed.connect(lambda err: self.can_update_ui() and QMessageBox.warning(self, "删除失败", f"无法删除: {err}"))
            self.register_worker(worker)

    def closeEvent(self, event):
        self.is_closing = True
        self.poll_timer.stop()
        self.refresh_generation += 1
        super().closeEvent(event)
