import threading
from src.config.settings import settings

MODEL_SEMAPHORE = threading.BoundedSemaphore(settings.agent_max_concurrency)

def safe_invoke(chain, payload, timeout=60):
    acquired = MODEL_SEMAPHORE.acquire(timeout=timeout)
    if not acquired:
        raise RuntimeError("模型服务繁忙，请稍后重试")
    try:
        return chain.invoke(payload)
    finally:
        MODEL_SEMAPHORE.release()
