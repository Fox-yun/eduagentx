from pydantic import BaseModel, Field
from typing import List

class QuizItemSchema(BaseModel):
    type: str = Field(..., description="题目类型，例如 'choice' 或 'essay'")
    question: str = Field(..., description="题目内容")
    options: List[str] = Field(default_factory=list, description="选项列表（如果有）")
    answer: str = Field(..., description="参考答案")
    explanation: str = Field(..., description="详细解析")

class QuizResourceSchema(BaseModel):
    quizzes: List[QuizItemSchema] = Field(..., description="练习题列表")
