from pydantic import BaseModel, Field

class StudentProfileSchema(BaseModel):
    """大模型提取学生画像的结构化输出定义"""
    major: str = Field(default="未知", description="学生的专业背景，如'软件工程', '汉语言文学', '高中生'等，若未提及则填'未知'")
    foundation: str = Field(default="未知", description="学生的领域知识基础，仅限：'零基础', '入门', '熟练', '未知'")
    cognitive_style: str = Field(default="未知", description="学生的认知风格偏好，仅限：'图文驱动', '案例驱动', '公式推导', '代码实战', '未知'")
    learning_goal: str = Field(default="未知", description="学生的学习终极目标，如'期末复习', '做项目', '纯了解', '未知'")
    weakness: str = Field(default="未知", description="学生的痛点或薄弱点，如'数学基础差', '编程弱', '概念记不住', '未知'")
    learning_pace: str = Field(default="未知", description="学生的学习节奏偏好，仅限：'速成突破', '按部就班', '深度探究', '未知'")
    time_budget: str = Field(default="未知", description="学生的学习时间预算，如'碎片化时间', '周末大块时间', '充裕', '未知'")
    emotional_state: str = Field(default="未知", description="学生的学习情绪状态，如'焦虑', '迷茫', '好奇', '自信', '未知'")
    preferred_format: str = Field(default="未知", description="学生偏好的系统回复风格，如'通俗白话', '严谨学术', '代码驱动', '未知'")

from typing import Literal, Dict, Any, Optional

class ResourceEnvelope(BaseModel):
    type: str
    status: Literal["pending", "running", "completed", "failed", "cancelled"]
    format: Literal["markdown", "json", "mermaid"]
    title: str
    data: Dict[str, Any]
    error: Optional[str] = None
    quality: Dict[str, Any] = Field(default_factory=dict)

class LearningEvaluation(BaseModel):
    """学习闭环：动态评估的结构化输出定义"""
    mastery_level: str = Field(description="掌握程度，如：'优秀', '良好', '薄弱'")
    weak_points: list[str] = Field(description="发现的具体薄弱知识点列表")
    remedial_suggestion: str = Field(description="针对薄弱点的学习建议")
    score: int = Field(description="量化评分(0-100)")
