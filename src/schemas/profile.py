from typing import Optional
from pydantic import BaseModel, Field

class StudentProfileSchema(BaseModel):
    major: str = Field(default="未知", description="专业背景，如未提及则为'未知'")
    foundation: str = Field(default="一般", description="知识基础，仅限：'零基础','入门','熟练','未知'")
    cognitive_style: str = Field(default="未识别", description="认知偏好，仅限：'图文驱动','案例驱动','公式推导','代码实战','未知'")
    learning_goal: str = Field(default="未明确", description="学习目标，未提及则为'未知'")
    weakness: str = Field(default="未说明", description="痛点或薄弱点，如'数学差','编程弱'，未提及则为'未知'")
    learning_pace: str = Field(default="适中", description="学习节奏偏好，仅限：'速成突破','按部就班','深度探究','未知'")
    time_budget: str = Field(default="未说明", description="学习时间预算，如'碎片化','大块时间'，未提及则为'未知'")
    emotional_state: str = Field(default="正常", description="情绪状态，如'焦虑','迷茫','好奇','自信'，未提及则为'未知'")
    preferred_format: str = Field(default="通俗白话", description="偏好风格，如'通俗白话','严谨学术'，未提及则为'未知'")

class StudentProfileDeltaSchema(BaseModel):
    major: Optional[str] = Field(default=None)
    foundation: Optional[str] = Field(default=None)
    cognitive_style: Optional[str] = Field(default=None)
    learning_goal: Optional[str] = Field(default=None)
    weakness: Optional[str] = Field(default=None)
    learning_pace: Optional[str] = Field(default=None)
    time_budget: Optional[str] = Field(default=None)
    emotional_state: Optional[str] = Field(default=None)
    preferred_format: Optional[str] = Field(default=None)
