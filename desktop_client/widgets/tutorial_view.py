import os
import json
import base64
import hashlib
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTextBrowser
from PyQt6.QtCore import QUrl
from desktop_client.utils.markdown_renderer import MarkdownRenderer

class TutorialView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.web_view = None
        self.fallback_browser = QTextBrowser()
        self.md_renderer = MarkdownRenderer()
        
        self.current_signature = None
        self.pending_payload = None
        self.use_webengine = False
        self.is_loaded = False
        
        self._setup_ui()
        self._try_initialize_webengine()

    def _setup_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(self.fallback_browser)

    def _try_initialize_webengine(self):
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            self.use_webengine = True
            self.web_view = QWebEngineView()
            self.layout.removeWidget(self.fallback_browser)
            self.fallback_browser.hide()
            self.layout.addWidget(self.web_view)
            
            # Load static renderer
            current_dir = os.path.dirname(os.path.abspath(__file__))
            index_path = os.path.join(current_dir, "..", "tutorial_renderer", "dist", "index.html")
            
            TUTORIAL_RENDERER_VERSION = "1.1.0"
            url = QUrl.fromLocalFile(os.path.abspath(index_path))
            url.setQuery(f"renderer_version={TUTORIAL_RENDERER_VERSION}")
            
            self.web_view.load(url)
            
            # When page loads, run pending payload
            self.web_view.loadFinished.connect(self._on_load_finished)
        except ImportError:
            self.use_webengine = False
            self.is_loaded = True
            
    def _on_load_finished(self, ok):
        self.is_loaded = True
        if ok and self.pending_payload:
            self._render_with_webengine(self.pending_payload)
            self.pending_payload = None

    def build_signature(self, markdown: str, widgets: list[dict]) -> str:
        data = json.dumps(
            {
                "renderer_version": "1.1.0",
                "markdown": markdown,
                "widgets": widgets,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(data.encode("utf-8")).hexdigest()
        
    def load_resource(self, markdown: str, widgets: list[dict] = None, task_id: str = ""):
        widgets = widgets or []
        sig = self.build_signature(markdown, widgets)
        if sig == self.current_signature:
            return
            
        self.current_signature = sig
        
        payload = {
            "task_id": task_id,
            "markdown": markdown,
            "widgets": widgets
        }
        
        if self.use_webengine:
            if not self.is_loaded:
                self.pending_payload = payload
            else:
                self._render_with_webengine(payload)
        else:
            self._render_with_fallback(payload)
            
    def _render_with_webengine(self, payload: dict):
        payload_json = json.dumps(payload, ensure_ascii=False)
        payload_b64 = base64.b64encode(payload_json.encode("utf-8")).decode("ascii")
        safe_argument = json.dumps(payload_b64)
        script = f"if(window.eduTutorial) {{ window.eduTutorial.renderBase64({safe_argument}); }} else {{ window._pendingTutorialPayload = {safe_argument}; }}"
        self.web_view.page().runJavaScript(script)
        
    def _render_with_fallback(self, payload: dict):
        markdown = payload.get("markdown", "")
        widgets = payload.get("widgets", [])
        
        html = self.md_renderer.render_markdown(markdown)
        
        if widgets:
            html += "<hr><h3>互动练习（静态模式）</h3>"
            for i, w in enumerate(widgets, 1):
                html += f"<h4>{i}. {w.get('title', '练习')}</h4>"
                wtype = w.get("type")
                if wtype == "inline_quiz":
                    html += f"<p><strong>问题：</strong>{w.get('question', '')}</p>"
                    for opt in w.get("options", []):
                        html += f"<div>- {opt.get('text', '')}</div>"
                    html += f"<p><strong>正确答案ID：</strong>{w.get('correct_option_id', '')}</p>"
                    html += f"<p><strong>解析：</strong>{w.get('explanation', '')}</p>"
                elif wtype == "sequence_sort":
                    html += "<p><strong>待排序步骤：</strong></p><ul>"
                    for item in w.get("items", []):
                        html += f"<li>{item.get('text', '')}</li>"
                    html += "</ul>"
                    html += "<p><strong>参考顺序（ID）：</strong>" + ", ".join(w.get("correct_order", [])) + "</p>"
                elif wtype == "matching_pairs":
                    html += "<p><strong>匹配项：</strong></p><ul>"
                    for pair in w.get("pairs", []):
                        left_obj = pair.get('left', '')
                        right_obj = pair.get('right', '')
                        left_text = left_obj.get('text', '') if isinstance(left_obj, dict) else str(left_obj)
                        right_text = right_obj.get('text', '') if isinstance(right_obj, dict) else str(right_obj)
                        html += f"<li>{left_text} <=> {right_text}</li>"
                    html += "</ul>"
                elif wtype == "stepper_tutorial":
                    for step in w.get("steps", []):
                        html += f"<div><strong>{step.get('title', '')}</strong>: {step.get('content', '')} (提示: {step.get('hint', '')})</div>"
                        
        self.fallback_browser.setHtml(f"<div style='padding:20px; color:#333333;'>{html}</div>")

    def clear(self):
        self.current_signature = None
        self.pending_payload = None
        if self.use_webengine and self.web_view:
            self.web_view.page().runJavaScript("if(window.eduTutorial) { document.getElementById('content').innerHTML = ''; }")
        elif self.fallback_browser:
            self.fallback_browser.clear()
