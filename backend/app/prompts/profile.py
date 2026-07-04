"""Prompt templates for the conversational profile extraction agent.

Phase 3.6: Conversational 8-Dimensional Learner Profile
"""

# ──────────────────────────────────────────────
# Profile Conversation System Prompt
# ──────────────────────────────────────────────

PROFILE_CONVERSATION_SYSTEM = """你是一个专业的学习画像分析师。你的任务是通过自然对话，分析学习者的八维学习画像。

## 八个核心维度

1. knowledge_depth — 当前知识基础深度（0-1 浮点数）
2. prerequisite_mastery — 先修知识掌握情况（0-1 浮点数）
3. concept_grasp — 概念理解能力（0-1 浮点数）
4. problem_solving — 问题解决能力（0-1 浮点数）
5. practice_ability — 动手练习与迁移能力（0-1 浮点数）
6. learning_pace — 学习节奏和消化速度（"slow" / "moderate" / "fast"）
7. resource_preference — 资源偏好（字符串数组，如 ["mind_map", "worked_examples", "quiz"]）
8. error_pattern — 常见错误模式和薄弱点（字典，键为错误模式名，值为 0-1 分数）

## 你的工作流程

1. 分析用户的最新回答
2. 从回答中提取已涉及的维度信号
3. 判断哪些维度还缺失
4. 生成下一个追问问题（如果还需要继续）

## 追问优先级

1. 学习目标是否清晰
2. 当前知识基础
3. 先修薄弱点
4. 学习时间和节奏
5. 资源偏好
6. 练习能力
7. 常见错误或担忧

## 输出格式

你必须返回严格的 JSON，格式如下：

{
  "extracted_dimensions": [
    {
      "dimension": "knowledge_depth",
      "value": 0.35,
      "confidence": 0.7,
      "evidence_text": "用户说'我会一点Python基础'",
      "rationale_summary": "用户表示有基础Python经验但不太深入"
    }
  ],
  "missing_dimensions": ["resource_preference", "practice_ability"],
  "next_question": "你更希望通过项目案例学习，还是先系统看概念？",
  "ready_to_finalize": false
}

## 限制

- confidence 必须在 [0, 1] 范围内
- evidence_text 只能来自用户原话的摘要
- 不允许返回 user_id、path_id 或任何系统内部信息
- 如果用户回答不足以提取任何维度，extracted_dimensions 返回空数组
- 如果已收集足够信息（至少6个维度覆盖，平均置信度≥0.65），ready_to_finalize 设为 true
"""


def build_profile_conversation_user_message(
    learning_goal: str,
    conversation_history: list[dict[str, str]],
    user_message: str,
    covered_dimensions: list[str],
    turn_count: int,
) -> str:
    """Build the user message for the profile conversation LLM call.

    Args:
        learning_goal: The user's learning goal description
        conversation_history: List of previous messages as {role, content} dicts
        user_message: The latest user message
        covered_dimensions: Dimensions already extracted with confidence > 0
        turn_count: Current turn number (0-indexed)

    Returns:
        Formatted user message string for the LLM
    """
    history_text = ""
    if conversation_history:
        for msg in conversation_history:
            role_label = "用户" if msg["role"] == "user" else "系统"
            history_text += f"{role_label}: {msg['content']}\n"

    covered_text = ", ".join(covered_dimensions) if covered_dimensions else "无"

    return f"""## 学习目标
{learning_goal}

## 对话历史
{history_text}

## 用户最新回答
{user_message}

## 当前状态
- 已覆盖维度: {covered_text}
- 当前轮次: {turn_count + 1} / 7

请分析用户的最新回答，提取维度信号，并生成下一步追问或准备结束。
"""


def build_initial_question(learning_goal: str) -> str:
    """Generate the initial question for a new profile conversation.

    Args:
        learning_goal: The user's learning goal description

    Returns:
        Initial question string
    """
    return (
        f"感谢你分享了学习目标：「{learning_goal}」。"
        f"为了给你规划最合适的学习路径，我需要先了解一些背景信息。\n\n"
        f"你目前对这个领域的基础了解有多少？比如之前是否学过相关内容？"
    )


# Fallback questions when LLM is not available
FALLBACK_QUESTIONS = [
    "你目前对这个领域的基础了解有多少？比如之前是否学过相关内容？",
    "你每天大概能花多少时间学习？你更偏好快节奏还是慢节奏？",
    "你更喜欢通过什么方式学习？比如看视频、读文档、做项目、刷题？",
    "你在学习新知识时，更容易在哪方面遇到困难？是概念理解还是动手实践？",
    "你之前在学习中遇到过哪些常见错误或困难？",
    "你对先修知识的掌握情况如何？有没有明显薄弱的部分？",
    "你更希望系统学习还是通过项目实战来掌握？",
]
