import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    llm_model_name: str = os.getenv("LLM_MODEL_NAME", "deepseek-ai/DeepSeek-V3")
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    agent_max_concurrency: int = int(os.getenv("AGENT_MAX_CONCURRENCY", "3"))
    model_request_timeout: int = int(os.getenv("MODEL_REQUEST_TIMEOUT", "60"))
    model_max_retries: int = int(os.getenv("MODEL_MAX_RETRIES", "1"))
    profile_request_timeout: int = int(os.getenv("PROFILE_REQUEST_TIMEOUT", "25"))
    task_poll_interval: int = int(os.getenv("TASK_POLL_INTERVAL", "2"))
    
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
