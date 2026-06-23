from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QVBoxLayout
from PyQt6.QtCore import Qt, QEvent

class HistoryItemWidget(QWidget):
    def __init__(self, text: str, status: str, mode: str, delete_callback, item, is_current: bool = False):
        super().__init__()
        self.item = item
        self.delete_callback = delete_callback
        self.full_text = text or "历史会话"
        self.status = status
        self.mode = mode
        self.is_current = is_current

        self.setup_ui()
        
    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 8, 8)
        layout.setSpacing(8)
        
        # Current Item Highlight
        if self.is_current:
            self.setStyleSheet("QWidget { background-color: #EFF6FF; border-left: 3px solid #2563EB; }")
        else:
            self.setStyleSheet("QWidget { background-color: transparent; border-left: 3px solid transparent; }")

        # Status Dot
        self.status_dot = QLabel()
        self.status_dot.setFixedSize(8, 8)
        self.update_status_dot()
        layout.addWidget(self.status_dot, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        # Text Layout
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        
        self.title_label = QLabel(self.full_text)
        self.title_label.setStyleSheet("font-size: 13px; color: #111827; font-weight: bold;" if self.is_current else "font-size: 13px; color: #374151;")
        
        self.subtitle_label = QLabel(self.mode)
        self.subtitle_label.setStyleSheet("font-size: 11px; color: #6B7280;")
        
        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self.subtitle_label)
        
        layout.addLayout(text_layout, 1)

        # Delete Button (Hidden by default)
        self.delete_btn = QPushButton("×")
        self.delete_btn.setFixedSize(20, 20)
        self.delete_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #9CA3AF;
                border: none;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                color: #DC2626;
                background-color: #FEE2E2;
                border-radius: 4px;
            }
        """)
        self.delete_btn.clicked.connect(lambda: self.delete_callback(self.item))
        self.delete_btn.setVisible(False)
        layout.addWidget(self.delete_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        
        # Install event filter for hover
        self.installEventFilter(self)

    def update_status_dot(self):
        color = "#9CA3AF"
        if self.status == "completed":
            color = "#16A34A"
        elif self.status == "failed" or self.status == "cancelled":
            color = "#DC2626"
        elif self.status == "running" or self.status == "pending":
            color = "#3B82F6"
            
        self.status_dot.setStyleSheet(f"background-color: {color}; border-radius: 4px;")

    def eventFilter(self, obj, event):
        if obj == self:
            if event.type() == QEvent.Type.Enter:
                self.delete_btn.setVisible(True)
            elif event.type() == QEvent.Type.Leave:
                self.delete_btn.setVisible(False)
        return super().eventFilter(obj, event)
