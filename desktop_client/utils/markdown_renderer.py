import re
import hashlib
import base64
import json
import requests
import urllib.parse
import markdown
from PyQt6.QtWidgets import (
    QLabel, QFrame, QVBoxLayout, QWidget, QButtonGroup, 
    QRadioButton, QTextEdit, QPushButton, QTableWidget, 
    QTableWidgetItem, QHeaderView, QAbstractItemView
)

class MarkdownRenderer:
    def __init__(self):
        self._latex_cache = {}
        self._mermaid_cache = {}

    def render_markdown(self, text: str) -> str:
        block_pattern = re.compile(r'(\$\$|\\\[)(.*?)(\$\$|\\\])', re.DOTALL)
        
        def repl(match, is_block):
            code = match.group(2).strip()
            if not code:
                return match.group(0)

            code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()
            if code_hash in self._latex_cache:
                img_b64 = self._latex_cache[code_hash]
            else:
                encoded_code = urllib.parse.quote(code)
                url = f"https://latex.codecogs.com/png.latex?%5Cbg_white%20%5Cdpi%7B120%7D%20%5Clarge%20{encoded_code}"
                try:
                    resp = requests.get(url, timeout=2)
                    if resp.status_code == 200:
                        img_b64 = base64.b64encode(resp.content).decode('utf-8')
                        self._latex_cache[code_hash] = img_b64
                    else:
                        img_b64 = None
                except Exception:
                    img_b64 = None

            if img_b64:
                if is_block:
                    return f'<div style="text-align:center; margin: 10px 0;"><img src="data:image/png;base64,{img_b64}" alt="math" /></div>'
                else:
                    return f'<img src="data:image/png;base64,{img_b64}" alt="math" style="vertical-align: middle;" />'
            else:
                return match.group(0)

        text = block_pattern.sub(lambda m: repl(m, True), text)
        
        inline_pattern = re.compile(r'(?<!\$)\$(?!\$)(.*?)(?<!\$)\$(?!\$)|\\\((.*?)\\\)', re.DOTALL)
        def inline_repl(match):
            code = match.group(1) if match.group(1) is not None else match.group(2)
            if code is None:
                return match.group(0)
            class PseudoMatch:
                def group(self, idx):
                    if idx == 0: return match.group(0)
                    if idx == 2: return code
                    return ""
            return repl(PseudoMatch(), False)

        text = inline_pattern.sub(inline_repl, text)
        return markdown.markdown(text, extensions=["tables", "fenced_code"])

    def process_mermaid(self, value: str) -> str:
        if "```" not in value:
            value = f"```mermaid\n{value}\n```"
        
        def mermaid_repl(match):
            code = match.group(1).strip()
            import html
            escaped_code = html.escape(code)
            
            code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()
                
            img_html = ""
            if code_hash in self._mermaid_cache:
                img_html = self._mermaid_cache[code_hash]
            else:
                j = {"code": code, "mermaid": {"theme": "default"}}
                encoded = base64.b64encode(json.dumps(j).encode('utf-8')).decode('utf-8')
                url = f"https://mermaid.ink/img/{encoded}"
                try:
                    resp = requests.get(url, timeout=2)
                    if resp.status_code == 200:
                        img_b64 = base64.b64encode(resp.content).decode('utf-8')
                        img_html = f'<div style="text-align:center;"><img src="data:image/png;base64,{img_b64}" alt="Mermaid Diagram Preview" /></div>'
                        self._mermaid_cache[code_hash] = img_html
                except Exception:
                    pass
                    
            source_block = f'<pre style="background-color:#F8FAFC; padding:12px; border:1px solid #E2E8F0; border-radius:4px; font-family:Consolas, monospace; font-size:13px; color:#334155; overflow-x:auto;">{escaped_code}</pre>'
            
            if img_html:
                return img_html + '<div style="color:#64748B; font-size:12px; margin-top:20px; margin-bottom:4px;"><b>🔍 Mermaid 源码（防断网兜底）：</b></div>' + source_block
            else:
                return '<div style="color:#DC2626; font-size:12px; margin-bottom:4px;"><b>⚠️ 图片预览加载失败（可能无网络），请参考以下源码：</b></div>' + source_block
            
        return re.sub(r'```(?:mermaid)?\s*(.*?)\s*```', mermaid_repl, value, flags=re.DOTALL)

    def render_html_content(self, html_body: str) -> str:
        return f"""
        <style>
            table {{ border-collapse: collapse; width: 100%; margin-bottom: 1em; }}
            th, td {{ border: 1px solid #CBD5E1; padding: 8px; text-align: left; }}
            th {{ background-color: #F1F5F9; font-weight: bold; color: #0F172A; }}
            pre {{ background-color: #F8FAFC; padding: 12px; border: 1px solid #E2E8F0; border-radius: 6px; overflow-x: auto; font-family: Consolas, monospace; }}
            code {{ background-color: #F1F5F9; padding: 2px 4px; border-radius: 4px; font-family: Consolas, monospace; color: #D97706; }}
            blockquote {{ border-left: 4px solid #2563EB; margin: 0; padding-left: 12px; color: #64748B; }}
            h1 {{ font-size: 20px; }}
            h2 {{ font-size: 17px; }}
            h3 {{ font-size: 15px; }}
        </style>
        <div style="font-family:'Microsoft YaHei UI', -apple-system, sans-serif; color:#1E293B; line-height:1.7;">
            {html_body}
        </div>
        """

    def render_quiz(self, quiz_data: str, references_md: str, layout: QVBoxLayout):
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
                
        json_str = quiz_data
        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', quiz_data)
        if match:
            json_str = match.group(1).strip()
        else:
            start = json_str.find('[')
            end = json_str.rfind(']')
            if start != -1 and end != -1:
                json_str = json_str[start:end+1]
            
        try:
            questions = json.loads(json_str)
        except Exception as e:
            fallback_label = QLabel(self.render_markdown(quiz_data))
            fallback_label.setWordWrap(True)
            fallback_label.setStyleSheet("color:#334155; line-height:1.7; font-size: 14px;")
            layout.addWidget(fallback_label)
            return

        for idx, q in enumerate(questions, 1):
            q_type = q.get("type", "choice")
            q_text = q.get("question", "")
            options = q.get("options", [])
            answer = q.get("answer", "")
            explanation = q.get("explanation", "")
            
            q_card = QFrame()
            q_card.setStyleSheet("QFrame { border: 1px solid #E2E8F0; border-radius: 12px; background-color: #FFFFFF; margin-bottom: 14px; }")
            q_layout = QVBoxLayout(q_card)
            q_layout.setContentsMargins(16, 16, 16, 16)
            
            title_label = QLabel(f"<b>{idx}. {'[选择题]' if q_type == 'choice' else '[简答题]'}</b> {q_text}")
            title_label.setWordWrap(True)
            title_label.setStyleSheet("font-size: 14px; color: #111827; border: none; background: transparent;")
            q_layout.addWidget(title_label)
            
            if q_type == "choice":
                btn_group = QButtonGroup(q_card)
                for opt in options:
                    rb = QRadioButton(opt)
                    rb.setStyleSheet("QRadioButton { font-size: 13px; color: #334155; border: none; background: transparent; padding: 4px; }")
                    q_layout.addWidget(rb)
                    btn_group.addButton(rb)
            else:
                text_edit = QTextEdit()
                text_edit.setPlaceholderText("请输入你的答案...")
                text_edit.setFixedHeight(80)
                text_edit.setStyleSheet("QTextEdit { border: 1px solid #E5E7EB; border-radius: 8px; background: #FFFFFF; }")
                q_layout.addWidget(text_edit)
                
            ans_widget = QWidget()
            ans_layout = QVBoxLayout(ans_widget)
            ans_layout.setContentsMargins(0, 10, 0, 0)
            
            ans_label = QLabel(f"<span style='color:#16A34A; font-weight:bold;'>正确答案：{answer}</span><br><br><span style='color:#475569;'><b>解析：</b>{explanation}</span>")
            ans_label.setWordWrap(True)
            ans_label.setStyleSheet("border: none; background: transparent; line-height: 1.7;")
            ans_layout.addWidget(ans_label)
            ans_widget.setVisible(False)
            
            btn = QPushButton("查看答案")
            btn.setObjectName("PrimaryButton")
            btn.setFixedWidth(100)
            btn.clicked.connect(lambda checked, w=ans_widget, b=btn: (w.setVisible(True), b.setVisible(False)))
            
            q_layout.addWidget(btn)
            q_layout.addWidget(ans_widget)
            
            layout.addWidget(q_card)
            
        if references_md:
            ref_label = QLabel(self.render_markdown(references_md))
            ref_label.setWordWrap(True)
            ref_label.setStyleSheet("color:#64748B; font-size:12px; margin-top: 20px;")
            layout.addWidget(ref_label)
            
        layout.addStretch()

    def render_plan(self, plan_data: str, references_md: str, layout: QVBoxLayout):
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
                
        json_str = plan_data
        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', plan_data)
        if match:
            json_str = match.group(1).strip()
        else:
            start = json_str.find('{')
            end = json_str.rfind('}')
            if start != -1 and end != -1:
                json_str = json_str[start:end+1]
            
        try:
            plan = json.loads(json_str)
        except Exception as e:
            fallback_label = QLabel(self.render_markdown(plan_data))
            fallback_label.setWordWrap(True)
            fallback_label.setStyleSheet("color:#334155; line-height:1.7; font-size: 14px;")
            layout.addWidget(fallback_label)
            return

        summary = plan.get("summary", "")
        if summary:
            summary_label = QLabel(f"<div style='background-color:#EFF6FF; color:#1E3A8A; padding:12px; border-radius:8px; border:1px solid #BFDBFE;'><b>计划概述：</b>{summary}</div>")
            summary_label.setWordWrap(True)
            layout.addWidget(summary_label)
            
        days = plan.get("days", [])
        if days:
            table = QTableWidget()
            table.setColumnCount(3)
            table.setHorizontalHeaderLabels(["天数", "建议时长", "核心任务"])
            table.setRowCount(len(days))
            table.horizontalHeader().setStretchLastSection(True)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            table.verticalHeader().setVisible(False)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
            table.setAlternatingRowColors(True)
            table.setStyleSheet("""
                QTableWidget {
                    border: 1px solid #E5E7EB;
                    border-radius: 8px;
                    background-color: #FFFFFF;
                    gridline-color: #E5E7EB;
                    margin-top: 14px;
                }
                QHeaderView::section {
                    background-color: #F8FAFC;
                    color: #111827;
                    font-weight: bold;
                    border: none;
                    border-bottom: 1px solid #E5E7EB;
                    padding: 10px;
                }
                QTableWidget::item {
                    padding: 10px;
                    color: #374151;
                }
            """)
            
            for row, d in enumerate(days):
                day_title = d.get("day", "")
                time_cost = d.get("time", "")
                focus = d.get("focus", "")
                
                table.setItem(row, 0, QTableWidgetItem(day_title))
                table.setItem(row, 1, QTableWidgetItem(time_cost))
                
                item_focus = QTableWidgetItem(focus)
                table.setItem(row, 2, item_focus)
            
            table.resizeRowsToContents()
            layout.addWidget(table)
            
        advice = plan.get("advice", "")
        if advice:
            advice_label = QLabel(f"<div style='margin-top:15px; color:#16A34A; padding:12px; border-left:4px solid #16A34A; background-color:#F0FDF4; border-radius: 4px;'><b>导师建议：</b>{advice}</div>")
            advice_label.setWordWrap(True)
            layout.addWidget(advice_label)
            
        if references_md:
            ref_label = QLabel(self.render_markdown(references_md))
            ref_label.setWordWrap(True)
            ref_label.setStyleSheet("color:#64748B; font-size:12px; margin-top: 20px;")
            layout.addWidget(ref_label)
            
        layout.addStretch()
