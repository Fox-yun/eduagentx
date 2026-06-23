import streamlit as st
import requests
import streamlit.components.v1 as components
import re

# 后端 API 地址
API_URL = "http://127.0.0.1:8000/api/chat/async"
TASK_URL = "http://127.0.0.1:8000/api/task"

# 页面配置
st.set_page_config(page_title="EduAgentX 智能教辅", page_icon="🎓", layout="wide")

st.title("🎓 EduAgentX: 多智能体个性化教辅系统")
st.markdown("基于大语言模型、RAG与多智能体协同机制的未来高校教育形态。")

# 初始化 Session State
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "student_profile" not in st.session_state:
    st.session_state.student_profile = {}

# 辅助函数：清理大模型输出的包裹标识符
def clean_markdown(text: str) -> str:
    text = text.strip()
    if text.startswith("```markdown"):
        text = text[len("```markdown"):].strip()
    elif text.startswith("```"):
        text = text[3:].strip()
    if text.endswith("```"):
        text = text[:-3].strip()
    return text

def render_mermaid(content):
    # Streamlit 1.35+ 原生支持 markdown 中的 mermaid 渲染
    st.markdown(content, unsafe_allow_html=True)
    
    # 兜底方案：如果大模型生成的 Mermaid 语法有误导致无法渲染，提供原始代码查看
    with st.expander("🛠️ 查看原始 Mermaid 代码 (若图表未显示或报错)"):
        st.code(content, language="markdown")

def extract_content(r):
    if isinstance(r, dict):
        if r.get("status") == "failed":
            return f"生成失败: {r.get('error', '')}"
        format_type = r.get("format")
        data = r.get("data", {})
        if format_type == "json":
            import json
            return "```json\n" + json.dumps(data, ensure_ascii=False, indent=2) + "\n```"
        else:
            return data.get("content", "")
    return str(r)

resource_map = {
    "doc": ("📄 课程讲义", lambda r: st.markdown(clean_markdown(extract_content(r)), unsafe_allow_html=True)),
    "quiz": ("📝 随堂测验", lambda r: st.markdown(clean_markdown(extract_content(r)), unsafe_allow_html=True)),
    "mindmap": ("🧠 思维导图", lambda r: render_mermaid(extract_content(r))),
    "plan": ("📅 学习计划", lambda r: st.markdown(clean_markdown(extract_content(r)), unsafe_allow_html=True)),
    "reading": ("📚 拓展阅读", lambda r: st.markdown(clean_markdown(extract_content(r)), unsafe_allow_html=True)),
    "code_case": ("💻 实操案例", lambda r: st.markdown(clean_markdown(extract_content(r)), unsafe_allow_html=True)),
    "ppt": ("📽️ 演示文稿", lambda r: st.markdown(clean_markdown(extract_content(r)), unsafe_allow_html=True)),
    "answer": ("💬 智能答疑", lambda r: st.markdown(clean_markdown(extract_content(r)), unsafe_allow_html=True)),
    "evaluation": ("📈 错题分析", lambda r: st.markdown(clean_markdown(extract_content(r)), unsafe_allow_html=True)),
    "remedial": ("💡 查漏补缺", lambda r: st.markdown(clean_markdown(extract_content(r)), unsafe_allow_html=True))
}

# 左侧侧边栏：展示动态画像
with st.sidebar:
    st.header("👤 实时学生画像")
    if not st.session_state.student_profile:
        st.info("系统暂未提取到足够的信息，请在对话框输入您的专业、基础等信息。")
    else:
        for k, v in st.session_state.student_profile.items():
            if v and v != "未知":
                # 中文映射映射
                key_map = {
                    "major": "专业背景",
                    "foundation": "知识基础",
                    "cognitive_style": "认知风格",
                    "learning_goal": "学习目标",
                    "weakness": "核心痛点",
                    "learning_pace": "学习节奏",
                    "time_budget": "时间预算",
                    "emotional_state": "当前情绪",
                    "preferred_format": "资料风格"
                }
                display_k = key_map.get(k, k)
                st.metric(label=display_k, value=v)

    st.markdown("---")
    st.header("⚙️ 资源生成设置")
    mode = st.selectbox("生成模式", ["快速模式", "完整模式", "答疑模式"], index=1)
    
    st.markdown("选择按需生成的资源：")
    resource_options = {
        "doc": "📄 课程讲义",
        "quiz": "📝 随堂测验",
        "plan": "📅 学习计划",
        "mindmap": "🧠 思维导图",
        "code_case": "💻 实操案例",
        "ppt": "📽️ 演示文稿",
        "reading": "📚 拓展阅读",
        "answer": "💬 智能答疑"
    }
    
    st.session_state.requested_resources = []
    for k, label in resource_options.items():
        if mode == "快速模式":
            default_val = k in ["doc", "quiz"]
        elif mode == "答疑模式":
            default_val = k in ["answer"]
        else:
            default_val = True
        
        if st.checkbox(label, value=default_val, key=f"check_{k}_{mode}"):
            st.session_state.requested_resources.append(k)

# 主聊天区域
chat_container = st.container()
with chat_container:
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            
            # 展示内嵌的 Trace
            if msg.get("trace"):
                with st.expander("🤖 多智能体协作过程"):
                    for item in msg["trace"]:
                        status_icon = "✅" if item["status"] == "success" else "⚠️"
                        latency = item.get("latency_ms")
                        latency_text = f" | {latency} ms" if latency else ""
                        st.markdown(
                            f"{status_icon} **{item['agent']}**：{item['message']}{latency_text}"
                        )

            # 展示内嵌的 Sources
            if msg.get("sources"):
                with st.expander("📌 RAG 检索参考依据"):
                    for item in msg["sources"]:
                        st.markdown(
                            f"**{item['chunk_id']}** | 来源：{item['source']} | 页码：{item['page']}"
                        )
                        st.caption(item["preview"])
            
            # 展示内嵌的生成资源
            if msg.get("resources"):
                resources = msg["resources"]
                active_keys = []
                for k in resource_map.keys():
                    if k in resources and resources[k]:
                        r = resources[k]
                        if isinstance(r, dict) and r.get("status") != "failed":
                            active_keys.append(k)
                        elif isinstance(r, str) and not r.startswith("生成失败"):
                            active_keys.append(k)
                
                if active_keys:
                    st.markdown("---")
                    st.subheader("📚 为您定制的学习资源全家桶")
                    tab_titles = [resource_map[k][0] for k in active_keys]
                    tabs = st.tabs(tab_titles)
                    
                    for idx, k in enumerate(active_keys):
                        with tabs[idx]:
                            resource_map[k][1](resources[k])

# 底部输入框
user_input = st.chat_input("跟你的智能助教聊聊你想学什么？(如: 我是文科生，我想学深度学习)")

if user_input:
    # 构造历史记录，过滤掉复杂的字典以节省带宽，只需要 role 和 content
    history_payload = [{"role": m["role"], "content": m["content"]} for m in st.session_state.chat_history]
    
    # 追加用户发言
    st.session_state.chat_history.append({"role": "user", "content": user_input})
    with chat_container:
        with st.chat_message("user"):
            st.markdown(user_input)
            
    # 请求后端 API
    with st.spinner("🚀 任务已提交，后台智能体正在协同处理中，请稍候..."):
        try:
            payload = {
                "user_input": user_input,
                "history": history_payload,
                "mode": mode,
                "requested_resources": st.session_state.requested_resources
            }
            response = requests.post(API_URL, json=payload)
            if response.status_code == 200:
                task_id = response.json().get("task_id")
                progress_bar = st.progress(0)
                status_text = st.empty()
                import time
                while True:
                    time.sleep(1)
                    res = requests.get(f"{TASK_URL}/{task_id}")
                    if res.status_code == 200:
                        task_data = res.json()
                        progress = task_data.get("progress", 0)
                        progress_bar.progress(progress / 100.0)
                        status_text.text(task_data.get("current_stage", "处理中..."))
                        is_terminal = task_data.get("is_terminal")
                        if is_terminal is None:
                            is_terminal = task_data.get("status") in {"completed", "partial_completed", "failed", "cancelled", "interrupted", "expired"}

                        if is_terminal:
                            st.session_state.student_profile = task_data.get("student_profile", {})
                            status_messages = {
                                "completed": "任务已完成。为您生成的专属教辅资源全家桶已经准备完毕，请查阅下方内容：",
                                "partial_completed": "任务部分完成。为您生成了部分教辅资源，请查阅下方内容：",
                                "failed": "任务执行失败。",
                                "cancelled": "任务已取消。",
                                "interrupted": "服务异常中断，可重新执行。",
                                "expired": "任务心跳超时，可重新执行。",
                            }
                            msg_content = status_messages.get(task_data.get("status"), "任务异常结束。")
                            st.session_state.chat_history.append({
                                "role": "assistant", 
                                "content": msg_content,
                                "resources": task_data.get("generated_resources", {}),
                                "trace": task_data.get("agent_trace", []),
                                "sources": task_data.get("retrieved_sources", [])
                            })
                            st.rerun()
                            break
            else:
                st.error(f"创建任务失败: {response.text}")
        except Exception as e:
            st.error(f"无法连接到后端服务器，请确保已启动 FastAPI (`uvicorn src.api.server:app`). 错误: {e}")
