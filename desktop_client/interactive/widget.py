from __future__ import annotations

import json
from urllib.parse import urlencode

from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtWidgets import (
    QFrame,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class InteractiveWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        from PyQt6.QtWebEngineWidgets import QWebEngineView

        self.current_resource: dict | None = None

        self.title_label = QLabel("互动学习工具")
        self.title_label.setObjectName("SectionTitle")
        
        self.description_label = QLabel(
            "适配的交互工具将在这里展示。"
        )
        self.description_label.setWordWrap(True)
        self.description_label.setObjectName("SectionSubTitle")

        self.web_view = QWebEngineView()
        self.web_view.setVisible(False)

        self.status_label = QLabel("暂无互动资源")
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.reload_button = QPushButton("重新加载")
        self.reload_button.setVisible(False)
        self.reload_button.clicked.connect(self.reload)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        layout.addWidget(self.title_label)
        layout.addWidget(self.description_label)
        layout.addWidget(self.status_label)
        layout.addWidget(self.web_view, 1)
        layout.addWidget(self.reload_button)

        self.web_view.loadStarted.connect(
            self._on_load_started
        )
        self.web_view.loadFinished.connect(
            self._on_load_finished
        )

    def load_resource(
        self,
        resource: dict,
        base_url: str,
        allowed_params: set[str],
    ) -> None:
        self.current_resource = resource

        self.title_label.setText(
            resource.get("title", "互动学习工具")
        )
        self.description_label.setText(
            resource.get("description", "")
        )

        raw_params = resource.get("initial_params", {})

        safe_params = {
            key: value
            for key, value in raw_params.items()
            if key in allowed_params
            and isinstance(value, (str, int, float, bool))
        }

        query = urlencode(safe_params)
        url = f"{base_url}/index.html"

        if query:
            url = f"{url}?{query}"

        self.web_view.setUrl(QUrl(url))

    def reload(self) -> None:
        self.web_view.reload()

    def _on_load_started(self) -> None:
        self.status_label.setText("正在加载互动工具……")
        self.status_label.setVisible(True)
        self.web_view.setVisible(False)
        self.reload_button.setVisible(False)

    def _on_load_finished(self, success: bool) -> None:
        if success:
            self.status_label.setVisible(False)
            self.web_view.setVisible(True)
            self.reload_button.setVisible(False)
        else:
            self.status_label.setText(
                "互动工具加载失败，请检查本地资源是否完整。"
            )
            self.status_label.setVisible(True)
            self.web_view.setVisible(False)
            self.reload_button.setVisible(True)
