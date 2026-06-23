import os
import time
from src.runtime.task_store import (
    create_task,
    request_task_cancel,
    update_task,
    get_task,
    complete_task,
    fail_task
)
from src.utils.progress import report_progress

# Using a test DB
os.environ["SQLITE_DB_PATH"] = "data/test_task_cancellation.db"

def test_cancel_blocks_progress():
    print("Testing if report_progress is blocked after cancel...")
    task_id = create_task("test_user", "test session", "test mode")

    # Request cancel
    request_task_cancel(task_id)

    # Try to report progress
    # Need a mock state
    state = {"task_id": task_id, "student_profile": {}}
    result = report_progress(state, 50, "Testing progress", student_profile={"new_key": "val"})

    print(f"report_progress returned: {result}")
    
    updated_task = get_task(task_id)
    print(f"Task progress after cancel: {updated_task['progress']}")
    print(f"Task profile after cancel: {updated_task.get('student_profile')}")

    if result is False and updated_task["progress"] == 0:
        print("=> SUCCESS: Progress was blocked.")
    else:
        print("=> FAIL: Progress was updated despite cancel.")

def test_cancel_blocks_update_task():
    print("Testing if update_task blocks generic status updates...")
    task_id = create_task("test_user_2", "test session", "test mode")

    request_task_cancel(task_id)

    try:
        update_task(task_id, status="failed")
    except Exception as e:
        print(f"update_task threw Exception: {e}")

    updated_task = get_task(task_id)
    print(f"Task status after try: {updated_task['status']}")

    if updated_task["status"] == "cancel_requested":
        print("=> SUCCESS: Status update was blocked.")
    else:
        print("=> FAIL: Status was updated despite cancel.")

def run_tests():
    try:
        os.remove("data/test_task_cancellation.db")
    except OSError:
        pass

    test_cancel_blocks_progress()
    print("-" * 40)
    test_cancel_blocks_update_task()

if __name__ == "__main__":
    run_tests()
