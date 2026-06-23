from pydantic import BaseModel, Field
from typing import List

class PlanDaySchema(BaseModel):
    day: str = Field(..., description="天数，例如 '第1天'")
    focus: str = Field(..., description="学习重点或核心任务")
    time: str = Field(..., description="建议时长，例如 '2小时'")

class LearningPlanSchema(BaseModel):
    summary: str = Field(..., description="整体计划概述")
    days: List[PlanDaySchema] = Field(default_factory=list, description="每日学习安排")
    advice: str = Field(..., description="专业指导建议或鼓励")
