from typing import Any, Dict
from src.runtime.task_store import update_active_task

def report_progress(
    state: Dict[str, Any],
    progress: int,
    stage: str,
    **payload
) -> bool:
    task_id = state.get("task_id")
    if not task_id:
        return False

    return update_active_task(
        task_id,
        progress=progress,
        current_stage=stage,
        **payload
    )
