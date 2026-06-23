import sys
import re

with open("desktop_client/widgets/main_window.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Remove PromptTextEdit and HistoryItemWidget
content = re.sub(r'class PromptTextEdit\(QTextEdit\):.*?class MainWindow', 'class MainWindow', content, flags=re.DOTALL)

# 2. Add imports
imports_to_add = """from desktop_client.widgets.prompt_edit import PromptInputCard
from desktop_client.widgets.history_item import HistoryItemWidget
from desktop_client.utils.markdown_renderer import MarkdownRenderer
"""
content = content.replace("from desktop_client.api_client import EduAgentApiClient", 
                          "from desktop_client.api_client import EduAgentApiClient\n" + imports_to_add)

# 3. Add markdown_renderer to __init__
content = content.replace("self.api_client = EduAgentApiClient()", 
                          "self.api_client = EduAgentApiClient()\n        self.md_renderer = MarkdownRenderer()")

# 4. Remove old render methods
content = re.sub(r'    def render_markdown\(self, text: str\) -> str:.*?    def on_task_failed', '    def on_task_failed', content, flags=re.DOTALL)

# 5. Replace input_card building logic
old_input_logic = """        # 输入卡片
        input_card = self.make_card()
        input_layout = QVBoxLayout(input_card)
        input_layout.setContentsMargins(16, 16, 16, 16)
        input_layout.setSpacing(12)

        input_header = QHBoxLayout()
        input_title = self.make_section_title("学习需求")
        input_desc = self.make_subtitle("描述你的课程、目标、基础和偏好，系统将生成个性化学习资源。")

        input_title_block = QWidget()
        input_title_layout = QVBoxLayout(input_title_block)
        input_title_layout.setContentsMargins(0, 0, 0, 0)
        input_title_layout.setSpacing(2)
        input_title_layout.addWidget(input_title)
        input_title_layout.addWidget(input_desc)

        input_header.addWidget(input_title_block)
        input_header.addStretch()

        input_layout.addLayout(input_header)

        self.input_box = PromptTextEdit()
        self.input_box.setObjectName("PromptInput")
        self.input_box.setPlaceholderText(
            "描述你的学习目标、知识基础和内容偏好……\\n"
            "Enter 发送，Shift+Enter 换行"
        )
        self.input_box.setFixedHeight(105)
        self.input_box.returnPressed.connect(self.start_task)
        self.input_box.setToolTip("Enter 发送；Shift+Enter 或 Ctrl+Enter 换行")
        input_layout.addWidget(self.input_box)

        action_bar = QHBoxLayout()
        action_bar.setSpacing(8)

        self.start_button = QPushButton("开始生成")
        self.start_button.setObjectName("PrimaryButton")
        self.start_button.clicked.connect(self.start_task)
        self.start_button.setToolTip("Enter 快捷发送，Shift+Enter 或 Ctrl+Enter 换行")

        self.demo_button = QPushButton("演示样例")
        self.demo_button.setObjectName("PurpleButton")
        self.demo_button.clicked.connect(self.fill_demo_input)

        self.new_session_button = QPushButton("新建会话")
        self.new_session_button.setObjectName("BlueButton")
        self.new_session_button.clicked.connect(self.start_new_session)

        self.stop_button = QPushButton("取消任务")
        self.stop_button.setObjectName("GrayButton")
        self.stop_button.clicked.connect(self.stop_polling)
        self.stop_button.setEnabled(False)

        self.export_button = QPushButton("导出结果")
        self.export_button.setObjectName("GreenButton")
        self.export_button.clicked.connect(self.export_result)

        action_bar.addWidget(self.start_button)
        action_bar.addWidget(self.demo_button)
        action_bar.addWidget(self.new_session_button)
        action_bar.addWidget(self.stop_button)
        action_bar.addWidget(self.export_button)
        action_bar.addStretch()

        input_layout.addLayout(action_bar)

        layout.addWidget(input_card)"""

new_input_logic = """        # 输入卡片
        self.input_card = PromptInputCard()
        self.input_card.submitted.connect(self.start_task_from_card)
        self.input_card.demo_btn.clicked.connect(self.fill_demo_input)
        
        # New Session / Stop buttons go next to or around here... wait, PromptInputCard has start, demo, clear.
        # We need "新建会话", "取消任务", "导出结果" globally. 
        # Actually we can put them in a small top action bar above the input card or below it.
        # Let's put a global action bar below the input card.
        global_action_bar = QHBoxLayout()
        global_action_bar.setSpacing(8)
        
        self.new_session_button = QPushButton("新建学习会话")
        self.new_session_button.setObjectName("BlueButton")
        self.new_session_button.clicked.connect(self.start_new_session)
        
        self.stop_button = QPushButton("取消任务")
        self.stop_button.setObjectName("GrayButton")
        self.stop_button.clicked.connect(self.stop_polling)
        self.stop_button.setEnabled(False)
        
        self.export_button = QPushButton("导出结果")
        self.export_button.setObjectName("GreenButton")
        self.export_button.clicked.connect(self.export_result)
        
        global_action_bar.addWidget(self.new_session_button)
        global_action_bar.addWidget(self.stop_button)
        global_action_bar.addWidget(self.export_button)
        global_action_bar.addStretch()
        
        layout.addWidget(self.input_card)
        layout.addLayout(global_action_bar)"""

content = content.replace(old_input_logic, new_input_logic)

# Replace usage of render_markdown
content = content.replace("self.render_markdown(", "self.md_renderer.render_markdown(")

with open("desktop_client/widgets/main_window.py", "w", encoding="utf-8") as f:
    f.write(content)
print("done")
