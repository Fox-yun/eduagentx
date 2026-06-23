from pydantic import BaseModel, Field

class AgentError(BaseModel):
    agent: str = Field(..., description="出错的智能体名称")
    status: str = Field(default="failed", description="状态，固定为 failed")
    message: str = Field(..., description="错误信息")

class SourceReference(BaseModel):
    chunk_id: str = Field(..., description="知识块ID")
    source: str = Field(..., description="来源文件")
    page: str = Field(..., description="页码")
    preview: str = Field(..., description="内容摘要预览")
