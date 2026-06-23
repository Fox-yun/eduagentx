import time

def add_trace(agent, status, message, start_time=None):
    latency_ms = None
    if start_time:
        latency_ms = int((time.time() - start_time) * 1000)

    return {
        "agent": agent,
        "status": status,
        "message": message,
        "latency_ms": latency_ms
    }
