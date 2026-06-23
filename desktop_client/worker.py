from PyQt6.QtCore import QThread, pyqtSignal
import time
from .api_client import EduAgentApiClient
from .config import POLL_INTERVAL_MS

CLIENT_TERMINAL_STATUSES = frozenset({
    "completed",
    "partial_completed",
    "failed",
    "cancelled",
    "interrupted",
    "expired",
})

class TaskWorker(QThread):
    task_updated = pyqtSignal(dict)
    task_failed = pyqtSignal(str)
    task_finished = pyqtSignal(dict)

    def __init__(self, api_client: EduAgentApiClient, task_id: str):
        super().__init__()
        self.client = api_client
        self.task_id = task_id
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        retries = 3
        while self._running and retries > 0:
            try:
                for task in self.client.stream_task(self.task_id):
                    if not self._running:
                        return
                        
                    if task.get("error"):
                        self.task_failed.emit(str(task["error"]))
                        return
                        
                    self.task_updated.emit(task)

                    is_terminal = task.get("is_terminal")
                    if is_terminal is None:
                        is_terminal = task.get("status") in CLIENT_TERMINAL_STATUSES

                    if is_terminal:
                        self.task_finished.emit(task)
                        return
                        
                # SSE ended without terminal state
                if self._running:
                    task = self.client.get_task(self.task_id)
                    is_terminal = task.get("is_terminal")
                    if is_terminal is None:
                        is_terminal = task.get("status") in CLIENT_TERMINAL_STATUSES
                    if is_terminal:
                        self.task_updated.emit(task)
                        self.task_finished.emit(task)
                        return
                    
                    retries -= 1
                    if retries > 0:
                        time.sleep(2)
                        continue
                        
            except Exception as e:
                retries -= 1
                if retries > 0:
                    time.sleep(2)
                    continue
                else:
                    self.task_failed.emit(f"连接异常: {str(e)}")
                    return

class CancelWorker(QThread):
    cancel_success = pyqtSignal(dict)
    cancel_failed = pyqtSignal(str)

    def __init__(self, api_client: EduAgentApiClient, task_id: str):
        super().__init__()
        self.client = api_client
        self.task_id = task_id

    def run(self):
        try:
            res = self.client.cancel_task(self.task_id)
            self.cancel_success.emit(res)
        except Exception as e:
            self.cancel_failed.emit(str(e))
