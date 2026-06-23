from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLabel, QPushButton, QCheckBox
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent

class PromptTextEdit(QTextEdit):
    returnPressed = pyqtSignal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        modifiers = event.modifiers()

        is_enter = key in (Qt.Key.Key_Return, Qt.Key.Key_Enter)

        if is_enter and modifiers == Qt.KeyboardModifier.NoModifier:
            if not self.isReadOnly():
                self.returnPressed.emit()
            event.accept()
            return

        super().keyPressEvent(event)

class PromptInputCard(QWidget):
    submitted = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        # Header
        header_layout = QHBoxLayout()
        title_layout = QVBoxLayout()
        title_layout.setSpacing(2)
        
        self.title_label = QLabel("学习需求")
        self.title_label.setStyleSheet("font-size: 15px; font-weight: bold; color: #111827;")
        
        self.desc_label = QLabel("描述你想学习的内容、当前基础和期望形式...")
        self.desc_label.setStyleSheet("font-size: 12px; color: #6B7280;")
        
        title_layout.addWidget(self.title_label)
        title_layout.addWidget(self.desc_label)
        
        header_layout.addLayout(title_layout)
        header_layout.addStretch()
        layout.addLayout(header_layout)
        
        # Status Label (Top 1)
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 13px; color: #2563EB; font-weight: bold;")
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)
        
        # Text Edit
        self.input_box = PromptTextEdit()
        self.input_box.setObjectName("PromptInput")
        self.input_box.setPlaceholderText("在这里输入...")
        self.input_box.setFixedHeight(105)
        self.input_box.returnPressed.connect(self.submit)
        self.input_box.textChanged.connect(self.update_counter)
        layout.addWidget(self.input_box)
        
        # Footer
        footer_layout = QHBoxLayout()
        
        self.shortcut_hint = QLabel("Enter 发送 · Shift+Enter 换行")
        self.shortcut_hint.setStyleSheet("font-size: 12px; color: #9CA3AF;")
        
        self.counter_label = QLabel("0 / 2000")
        self.counter_label.setStyleSheet("font-size: 12px; color: #9CA3AF;")
        
        footer_layout.addWidget(self.shortcut_hint)
        footer_layout.addStretch()
        footer_layout.addWidget(self.counter_label)
        
        layout.addLayout(footer_layout)
        
        # Resources Options
        self.resource_group = QHBoxLayout()
        self.resource_group.setSpacing(10)
        self.checkboxes = {}
        
        resources_options = {
            "doc": "讲义",
            "quiz": "练习",
            "plan": "计划",
            "mindmap": "导图",
            "code_case": "代码",
            "ppt": "PPT",
            "reading": "阅读",
            "answer": "答疑"
        }
        for k, label in resources_options.items():
            cb = QCheckBox(label)
            cb.setChecked(True)
            cb.setStyleSheet("font-size: 12px; color: #4B5563;")
            self.checkboxes[k] = cb
            self.resource_group.addWidget(cb)
        self.resource_group.addStretch()
        
        layout.addLayout(self.resource_group)
        
        # Actions
        self.action_layout = QHBoxLayout()
        self.action_layout.setSpacing(8)
        
        self.start_btn = QPushButton("开始生成")
        self.start_btn.setObjectName("PrimaryButton")
        self.start_btn.clicked.connect(self.submit)
        
        self.demo_btn = QPushButton("演示样例")
        self.demo_btn.setObjectName("PurpleButton")
        
        self.clear_btn = QPushButton("清空")
        self.clear_btn.setObjectName("GrayButton")
        self.clear_btn.clicked.connect(self.clear_input)
        
        self.action_layout.addWidget(self.start_btn)
        self.action_layout.addWidget(self.demo_btn)
        self.action_layout.addWidget(self.clear_btn)
        self.action_layout.addStretch()
        
        layout.addLayout(self.action_layout)
        
    def update_counter(self):
        text = self.input_box.toPlainText()
        length = len(text)
        self.counter_label.setText(f"{length} / 2000")
        if length > 2000:
            self.counter_label.setStyleSheet("font-size: 12px; color: #DC2626;")
            self.start_btn.setEnabled(False)
        else:
            self.counter_label.setStyleSheet("font-size: 12px; color: #9CA3AF;")
            self.start_btn.setEnabled(True)
            
    def submit(self):
        text = self.input_box.toPlainText().strip()
        if text and len(text) <= 2000:
            self.submitted.emit(text)
            
    def set_processing_state(self, is_processing: bool, text: str = ""):
        self.input_box.setReadOnly(is_processing)
        self.start_btn.setEnabled(not is_processing)
        if is_processing:
            summary = text[:36] + ("..." if len(text) > 36 else "")
            self.status_label.setText(f"正在处理：{summary}")
            self.status_label.setStyleSheet("font-size: 13px; color: #2563EB; font-weight: bold;")
            self.status_label.setVisible(True)
        else:
            if text:
                summary = text[:36] + ("..." if len(text) > 36 else "")
                self.status_label.setText(f"已完成：{summary}")
                self.status_label.setStyleSheet("font-size: 13px; color: #16A34A; font-weight: bold;")
            else:
                self.status_label.setVisible(False)
            
    def clear_input(self):
        self.input_box.clear()
        
    def set_text(self, text: str):
        self.input_box.setPlainText(text)

    def get_text(self) -> str:
        return self.input_box.toPlainText()

    def get_requested_resources(self) -> list:
        return [k for k, cb in self.checkboxes.items() if cb.isChecked()]

    def update_mode_defaults(self, mode: str):
        if mode == "快速模式":
            defaults = ["doc", "quiz"]
        elif mode == "答疑模式":
            defaults = ["answer"]
        else:
            defaults = list(self.checkboxes.keys())
            
        for k, cb in self.checkboxes.items():
            cb.setChecked(k in defaults)
