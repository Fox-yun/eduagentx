from typing import TypedDict, List, Dict, Any, Annotated, Optional
import operator

def merge_dict(a: Optional[Dict[str, Any]], b: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    result = {}
    if a:
        result.update(a)
    if b:
        result.update(b)
    return result

class AgentState(TypedDict, total=False):
    """
    EduAgentX 的核心状态定义。
    所有 Agent 都在读取并更新这个状态对象。
    """
    # 用户的原始请求与对话历史
    messages: List[str]
    
    # 动态构建的学生学习画像 (不少于6个维度)
    student_profile: Dict[str, Any]
    
    # 本轮临时偏好 (专业一点, 通俗一点等)
    request_preferences: Dict[str, Any]
    
    # 画像是否在当前轮次发生实质性变化
    profile_dirty: bool
    
    # Router 识别出的当前用户意图
    # 可选值: "want_to_learn" (想学新课), "want_to_practice" (想做题), "want_to_ask" (提问)
    current_intent: str
    
    # 生成的各类个性化学习资源结果
    generated_resources: Annotated[Dict[str, Any], merge_dict]
    
    # RAG 模块从本地知识库检索到的参考内容
    retrieved_context: str
    
    # 动态任务队列 (例如: ["doc_generator", "quiz_generator"])
    pending_tasks: List[str]
    
    # Reviewer 对生成内容的审查意见
    review_feedback: str
    
    # RAG 检索参考依据，包含来源与页码等元数据
    retrieved_sources: List[Dict[str, Any]]
    
    # 多智能体协作执行轨迹
    agent_trace: Annotated[List[Dict[str, Any]], operator.add]

    # 异步任务标识
    task_id: str
    
    # 任务全局截止时间 (阶段时间预算)
    task_deadline: float
    
    # 生成模式
    mode: str
    
    # 用户标识
    user_id: str
    
    # 会话标识
    conversation_id: str
    
    # 课程标识
    course_id: Optional[str]
