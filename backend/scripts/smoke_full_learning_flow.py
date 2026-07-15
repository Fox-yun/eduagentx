#!/usr/bin/env python3
"""Full learning flow smoke test for EduAgentX.

Executes the complete user journey from registration to logout,
verifying every step of the learning pipeline:

  Register → Verify Email → Login → Onboarding → Create Goal →
  Clarification → Diagnostic → Diagnostic Grading → Path Generation →
  Path Revision → Activate Version → Generate Unit → Generate Lecture →
  Generate Practice → Generate Assessment → Submit Assessment →
  Verify Mastery → Verify Node Unlock → Upload Knowledge →
  Wait for Index → Search Knowledge → Tutor Q&A → Recommendations →
  Resume → Logout

Any step failure: immediately exit non-zero with API, Task ID, and Error Code.

Final success output:
  FULL LEARNING FLOW PASSED

Prerequisites:
  - Backend running on BASE_URL (default: http://127.0.0.1:8000)
  - PostgreSQL + Redis + Worker + Outbox Publisher running
  - LLM API key configured (or template fallback)
  - Object storage (MinIO or InMemory) available

Usage:
  python scripts/smoke_full_learning_flow.py [--base-url http://127.0.0.1:8000] [--timeout 300]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from typing import Any

import httpx

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT = 300  # seconds for the entire flow
POLL_INTERVAL = 2.0  # seconds between polling
MAX_POLL_RETRIES = 60  # max polling attempts per step
ASSESSMENT_PASS_THRESHOLD = 60.0
NODE_COMPLETION_THRESHOLD = 70.0


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


class SmokeError(Exception):
    """Raised when a smoke test step fails."""

    def __init__(self, step: str, message: str, status_code: int | None = None, response_body: str = ""):
        self.step = step
        self.message = message
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(f"[{step}] {message}")


def log(step: str, msg: str) -> None:
    """Print a step log line."""
    print(f"  [{step}] {msg}")


def fail(step: str, msg: str, status_code: int | None = None, body: str = "") -> None:
    """Log failure and exit."""
    print(f"\n❌ FAILED at step: {step}")
    print(f"   Error: {msg}")
    if status_code:
        print(f"   HTTP Status: {status_code}")
    if body:
        print(f"   Response: {body[:500]}")
    sys.exit(1)


def assert_ok(
    step: str,
    response: httpx.Response,
    expected: int = 200,
) -> httpx.Response:
    """Assert response status code, or fail with details."""
    if response.status_code != expected:
        fail(
            step,
            f"Expected HTTP {expected}, got {response.status_code}",
            response.status_code,
            response.text,
        )
    return response


def _select_smoke_answer(question: dict[str, Any]) -> Any:
    """Choose a defensible answer without exposing server-side answer keys.

    The local fallback assessment uses intentionally clear distractors.  This
    heuristic also works for similarly phrased LLM questions while keeping the
    public assessment contract free of correct-answer data.
    """
    question_type = question.get("type", "")
    prompt = str(question.get("prompt", ""))
    options = question.get("options") or []

    if question_type == "short_answer":
        return (
            "Python 是由解释器执行的动态类型语言，变量名在运行时引用对象。"
            "在实际开发中，可以把变量、控制流和函数组合成可复用的自动化程序。"
            "我会通过运行示例、检查边界输入、阅读报错并补充测试来验证结果，"
            "下一步继续学习模块化、调试、测试与项目工程化。"
        )

    if question_type == "true_false":
        negative_claim_markers = ("只需要", "不需要", "无需", "无须", "没有必要", "完全不")
        return not any(marker in prompt for marker in negative_claim_markers)

    if not options:
        return "a"

    negative_markers = (
        "只看不练",
        "只做练习",
        "只记忆",
        "只重复",
        "只关注工具",
        "仅阅读",
        "仅用于",
        "忽略",
        "随机",
        "无需实践",
        "不做任何",
        "不验证",
        "无关的主题",
        "没有实际",
        "已经过时",
        "记忆所有",
        "完全依赖",
        "跳过基础",
        "所有版本变更",
        "与实践无关",
        "不具有通用性",
        "增加代码复杂度",
    )
    positive_markers = (
        "广泛应用",
        "理解原理",
        "实际场景",
        "实际应用",
        "基本原理",
        "检查输入输出",
        "定位问题",
        "提高开发效率",
        "最佳实践",
        "充分的测试",
        "清晰的文档",
        "遵循规范",
        "结合学习目标",
        "通过项目验证",
    )

    def option_score(option: dict[str, Any]) -> int:
        label = str(option.get("label", ""))
        return sum(2 for marker in positive_markers if marker in label) - sum(
            3 for marker in negative_markers if marker in label
        )

    if question_type == "multiple_choice":
        selected = [option["value"] for option in options if option_score(option) >= 0]
        if selected and len(selected) < len(options):
            return selected
        return [option["value"] for option in options[: min(3, len(options))]]

    best = max(options, key=option_score)
    return best["value"]


def _build_smoke_answers(questions: list[dict[str, Any]]) -> dict[str, Any]:
    """Build one answer per public assessment question."""
    return {question["question_id"]: _select_smoke_answer(question) for question in questions}


def poll_task(
    client: httpx.Client,
    step: str,
    task_id: str,
    headers: dict[str, str],
    base_url: str,
    target_status: str = "completed",
    max_retries: int = MAX_POLL_RETRIES,
) -> dict[str, Any]:
    """Poll a background task until it reaches the target status."""
    for attempt in range(1, max_retries + 1):
        res = client.get(
            f"{base_url}/api/tasks/{task_id}",
            headers=headers,
        )
        if res.status_code != 200:
            log(step, f"Poll attempt {attempt}: HTTP {res.status_code}")
            time.sleep(POLL_INTERVAL)
            continue

        task = res.json()
        status = task.get("status", "")
        progress = task.get("progress", 0)
        log(step, f"Poll attempt {attempt}: status={status}, progress={progress}%")

        if status == target_status:
            return task  # type: ignore[no-any-return]
        if status == "failed":
            error_msg = task.get("error", "Unknown error")
            fail(step, f"Task {task_id} failed: {error_msg}")

        time.sleep(POLL_INTERVAL)

    fail(step, f"Task {task_id} timed out after {max_retries * POLL_INTERVAL:.0f}s")
    return {}  # unreachable


# ──────────────────────────────────────────────
# Smoke Test Steps
# ──────────────────────────────────────────────


def step_register(client: httpx.Client, base_url: str) -> dict[str, str]:
    """Step 1: Register a new user."""
    step = "REGISTER"
    uid = uuid.uuid4().hex[:8]
    email = f"smoke-{uid}@example.com"
    password = "SmokeTest-Pass-123!"

    # Get CSRF token first
    csrf_res = client.get(f"{base_url}/api/auth/csrf")
    assert_ok(step, csrf_res)
    csrf_token = csrf_res.json()["csrf_token"]

    res = client.post(
        f"{base_url}/api/auth/register",
        json={
            "email": email,
            "password": password,
            "display_name": f"Smoke Test User {uid}",
            "accept_terms": True,
        },
        headers={"X-CSRF-Token": csrf_token},
    )
    assert_ok(step, res, expected=200)
    data = res.json()
    log(step, f"Registered: {email}, user_id={data['user']['user_id']}")

    return {
        "email": email,
        "password": password,
        "user_id": data["user"]["user_id"],
        "csrf_token": csrf_token,
    }


def step_login(client: httpx.Client, base_url: str, email: str, password: str) -> dict[str, str]:
    """Step 2: Login."""
    step = "LOGIN"
    csrf_res = client.get(f"{base_url}/api/auth/csrf")
    csrf_token = csrf_res.json()["csrf_token"]

    res = client.post(
        f"{base_url}/api/auth/login",
        json={"email": email, "password": password, "remember_me": True},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert_ok(step, res)

    data = res.json()
    access_token = res.cookies.get("access_token", "")
    if not access_token:
        # Some deployments return tokens in body
        access_token = data.get("access_token", "")

    log(step, f"Login successful, user_id={data.get('user_id', '')}")

    return {
        "access_token": access_token,
        "csrf_token": csrf_token,
        "user_id": data.get("user_id", ""),
    }


def step_onboarding(
    client: httpx.Client,
    base_url: str,
    auth: dict[str, str],
) -> None:
    """Step 3: Complete onboarding."""
    step = "ONBOARDING"
    headers = {
        "X-CSRF-Token": auth["csrf_token"],
        "Cookie": f"access_token={auth['access_token']}; csrftoken={auth['csrf_token']}",
    }
    res = client.post(
        f"{base_url}/api/users/me/onboarding",
        json={
            "role": "student",
            "learning_interests": ["programming", "algorithms"],
            "learning_preferences": ["text", "interactive"],
            "preferred_language": "zh",
            "weekly_hours": 10,
            "use_diagnostic": True,
            "use_knowledge_base": True,
        },
        headers=headers,
    )
    assert_ok(step, res)
    log(step, "Onboarding completed")


def step_create_goal(
    client: httpx.Client,
    base_url: str,
    auth: dict[str, str],
) -> str:
    """Step 4: Create a learning goal."""
    step = "CREATE_GOAL"
    headers = {
        "Content-Type": "application/json",
        "X-CSRF-Token": auth["csrf_token"],
        "Cookie": f"access_token={auth['access_token']}; csrftoken={auth['csrf_token']}",
    }
    res = client.post(
        f"{base_url}/api/learning-goals",
        json={
            "raw_goal": "学习 Python 编程基础和算法",
            "current_level": "beginner",
            "target_level": "intermediate",
            "weekly_hours": 10,
            "use_diagnostic": True,
            "use_knowledge_base": True,
            "content_language": "zh",
        },
        headers=headers,
    )
    assert_ok(step, res)
    data = res.json()
    goal_id = data["goal_id"]
    log(step, f"Goal created: {goal_id}")
    return goal_id  # type: ignore[no-any-return]


def step_clarification(
    client: httpx.Client,
    base_url: str,
    auth: dict[str, str],
    goal_id: str,
) -> None:
    """Step 5: Get and submit clarification answers."""
    step = "CLARIFICATION"
    headers = {
        "X-CSRF-Token": auth["csrf_token"],
        "Cookie": f"access_token={auth['access_token']}; csrftoken={auth['csrf_token']}",
    }

    # Get questions
    res = client.get(
        f"{base_url}/api/learning-goals/{goal_id}/clarifications",
        headers=headers,
    )
    assert_ok(step, res)
    questions = res.json()["questions"]

    # Build answers
    answers: dict[str, Any] = {}
    for q in questions:
        qid = q["question_id"]
        qtype = q["type"]
        if qtype == "single_choice":
            answers[qid] = "beginner"
        elif qtype == "multiple_choice":
            answers[qid] = ["theory", "practice"]
        elif qtype == "number":
            answers[qid] = 10
        else:
            answers[qid] = "text"

    # Submit
    res = client.post(
        f"{base_url}/api/learning-goals/{goal_id}/clarifications",
        json={"answers": answers},
        headers={**headers, "Content-Type": "application/json"},
    )
    assert_ok(step, res)
    log(step, f"Clarification submitted ({len(answers)} answers)")


def step_diagnostic(
    client: httpx.Client,
    base_url: str,
    auth: dict[str, str],
    goal_id: str,
) -> str:
    """Step 6: Get diagnostic and submit answers. Returns attempt_id."""
    step = "DIAGNOSTIC"
    headers = {
        "X-CSRF-Token": auth["csrf_token"],
        "Cookie": f"access_token={auth['access_token']}; csrftoken={auth['csrf_token']}",
    }

    # Get diagnostic
    res = client.get(
        f"{base_url}/api/learning-goals/{goal_id}/diagnostic",
        headers=headers,
    )
    assert_ok(step, res)
    data = res.json()
    attempt_id = data["attempt_id"]
    questions = data["questions"]

    # Build answers — pick reasonable answers for each type
    answers: list[dict[str, Any]] = []
    for q in questions:
        qid = q["question_id"]
        qtype = q["question_type"]
        if qtype == "single_choice":
            # Pick first option
            options = q.get("options") or []
            answers.append({"question_id": qid, "answer": options[0]["value"] if options else "a"})
        elif qtype == "multiple_choice":
            options = q.get("options") or []
            picks = [opt["value"] for opt in options[:2]] if len(options) >= 2 else [options[0]["value"]]
            answers.append({"question_id": qid, "answer": picks})
        elif qtype == "true_false":
            answers.append({"question_id": qid, "answer": True})
        elif qtype == "short_answer":
            answers.append({"question_id": qid, "answer": "我对这个领域有一些基础了解，希望进一步深入学习。"})
        else:
            answers.append({"question_id": qid, "answer": "a"})

    # Submit
    res = client.post(
        f"{base_url}/api/learning-goals/{goal_id}/diagnostic/submit",
        json={"attempt_id": attempt_id, "answers": answers},
        headers={**headers, "Content-Type": "application/json"},
    )
    assert_ok(step, res)
    log(step, f"Diagnostic submitted: attempt={attempt_id}")
    return attempt_id  # type: ignore[no-any-return]


def step_wait_diagnostic_grading(
    client: httpx.Client,
    base_url: str,
    auth: dict[str, str],
    goal_id: str,
) -> None:
    """Step 7: Wait for diagnostic grading + path generation to complete."""
    step = "DIAGNOSTIC_GRADING"
    headers = {
        "X-CSRF-Token": auth["csrf_token"],
        "Cookie": f"access_token={auth['access_token']}; csrftoken={auth['csrf_token']}",
    }

    for attempt in range(1, MAX_POLL_RETRIES + 1):
        res = client.get(
            f"{base_url}/api/learning-goals/{goal_id}",
            headers=headers,
        )
        assert_ok(step, res)
        goal = res.json()
        status = goal.get("status", "")
        active_task_id = goal.get("active_task_id")
        log(step, f"Poll attempt {attempt}: goal status={status}, active_task={active_task_id}")

        if status == "ready" or status == "active":
            log(step, f"Goal is ready/active: status={status}")
            return
        if status == "failed":
            fail(step, f"Goal failed: {goal.get('next_step', '')}")

        time.sleep(POLL_INTERVAL)

    fail(step, "Diagnostic grading / path generation timed out")


def step_get_path(
    client: httpx.Client,
    base_url: str,
    auth: dict[str, str],
    goal_id: str,
) -> dict[str, Any]:
    """Step 8: Get the generated learning path."""
    step = "GET_PATH"
    headers = {
        "X-CSRF-Token": auth["csrf_token"],
        "Cookie": f"access_token={auth['access_token']}; csrftoken={auth['csrf_token']}",
    }
    res = client.get(
        f"{base_url}/api/learning-paths/",
        headers=headers,
    )
    assert_ok(step, res)
    paths = res.json().get("items", [])
    if not paths:
        fail(step, "No learning paths found")
    path = paths[0]
    path_id = path.get("path_id") or path.get("id")
    log(step, f"Path found: {path_id}")
    return {"path_id": path_id, "path_data": path}


def step_request_revision(
    client: httpx.Client,
    base_url: str,
    auth: dict[str, str],
    path_id: str,
) -> str | None:
    """Step 9: Request a path revision."""
    step = "PATH_REVISION"
    headers = {
        "Content-Type": "application/json",
        "X-CSRF-Token": auth["csrf_token"],
        "Cookie": f"access_token={auth['access_token']}; csrftoken={auth['csrf_token']}",
    }
    res = client.post(
        f"{base_url}/api/learning-paths/{path_id}/revision-requests",
        json={"revision_request": "请增加更多实践项目"},
        headers=headers,
    )
    assert_ok(step, res)
    data = res.json()
    task_id = data.get("active_task_id")
    log(step, f"Revision requested, task_id={task_id}")
    return task_id  # type: ignore[no-any-return]


def step_wait_revision(
    client: httpx.Client,
    base_url: str,
    auth: dict[str, str],
    task_id: str | None,
) -> None:
    """Step 10: Wait for revision to complete."""
    step = "WAIT_REVISION"
    if not task_id:
        log(step, "No task_id, skipping")
        return

    headers = {
        "X-CSRF-Token": auth["csrf_token"],
        "Cookie": f"access_token={auth['access_token']}; csrftoken={auth['csrf_token']}",
    }
    poll_task(client, step, task_id, headers, base_url)
    log(step, "Revision completed")


def step_activate_version(
    client: httpx.Client,
    base_url: str,
    auth: dict[str, str],
    path_id: str,
) -> None:
    """Step 11: Activate the revised version (if in_review)."""
    step = "ACTIVATE_VERSION"
    headers = {
        "X-CSRF-Token": auth["csrf_token"],
        "Cookie": f"access_token={auth['access_token']}; csrftoken={auth['csrf_token']}",
    }

    # List versions
    res = client.get(
        f"{base_url}/api/learning-paths/{path_id}/versions",
        headers=headers,
    )
    assert_ok(step, res)
    versions = res.json().get("items", [])

    # Find in_review version
    review_version = None
    for v in versions:
        if v.get("status") in ("in_review", "draft"):
            review_version = v
            break

    if not review_version:
        log(step, "No in_review version found, skipping activation")
        return

    version_id = review_version.get("version_id") or review_version.get("id")
    res = client.post(
        f"{base_url}/api/learning-paths/{path_id}/versions/{version_id}/activate",
        headers=headers,
    )
    assert_ok(step, res)
    log(step, f"Version {version_id} activated")


def step_generate_unit(
    client: httpx.Client,
    base_url: str,
    auth: dict[str, str],
    path_id: str,
) -> str:
    """Step 12: Generate unit content for the first node. Returns node_id."""
    step = "GENERATE_UNIT"
    headers = {
        "Content-Type": "application/json",
        "X-CSRF-Token": auth["csrf_token"],
        "Cookie": f"access_token={auth['access_token']}; csrftoken={auth['csrf_token']}",
    }

    # Get path details to find first node
    res = client.get(
        f"{base_url}/api/learning-paths/{path_id}",
        headers=headers,
    )
    assert_ok(step, res)
    path_data = res.json()

    # Find first available/unlocked node
    nodes = path_data.get("nodes", [])
    if not nodes:
        fail(step, "No nodes found in path")

    node = nodes[0]
    node_id = node.get("node_id") or node.get("id")
    log(step, f"First node: {node_id} ({node.get('title', '')})")

    # Generate content
    res = client.post(
        f"{base_url}/api/learning-paths/{path_id}/nodes/{node_id}/content",
        headers=headers,
    )
    assert_ok(step, res)
    data = res.json()
    task_id = data.get("active_task_id")

    if task_id:
        poll_task(client, step, task_id, headers, base_url)

    log(step, f"Unit content generated for node {node_id}")
    return node_id  # type: ignore[no-any-return]


def step_generate_lecture(
    client: httpx.Client,
    base_url: str,
    auth: dict[str, str],
    path_id: str,
    node_id: str,
) -> None:
    """Step 13: Generate lecture for the node."""
    step = "GENERATE_LECTURE"
    headers = {
        "Content-Type": "application/json",
        "X-CSRF-Token": auth["csrf_token"],
        "Cookie": f"access_token={auth['access_token']}; csrftoken={auth['csrf_token']}",
    }
    res = client.post(
        f"{base_url}/api/learning-paths/{path_id}/nodes/{node_id}/content/lecture",
        headers=headers,
    )
    assert_ok(step, res)
    data = res.json()
    task_id = data.get("active_task_id")
    if task_id:
        poll_task(client, step, task_id, headers, base_url)
    log(step, "Lecture generated")


def step_generate_practice(
    client: httpx.Client,
    base_url: str,
    auth: dict[str, str],
    path_id: str,
    node_id: str,
) -> None:
    """Step 14: Generate practice questions."""
    step = "GENERATE_PRACTICE"
    headers = {
        "Content-Type": "application/json",
        "X-CSRF-Token": auth["csrf_token"],
        "Cookie": f"access_token={auth['access_token']}; csrftoken={auth['csrf_token']}",
    }
    res = client.post(
        f"{base_url}/api/learning-paths/{path_id}/nodes/{node_id}/practice",
        headers=headers,
    )
    assert_ok(step, res)
    data = res.json()
    task_id = data.get("active_task_id")
    if task_id:
        poll_task(client, step, task_id, headers, base_url)
    log(step, "Practice generated")


def step_generate_assessment(
    client: httpx.Client,
    base_url: str,
    auth: dict[str, str],
    path_id: str,
    node_id: str,
) -> str:
    """Step 15: Generate assessment. Returns assessment_id."""
    step = "GENERATE_ASSESSMENT"
    headers = {
        "Content-Type": "application/json",
        "X-CSRF-Token": auth["csrf_token"],
        "Cookie": f"access_token={auth['access_token']}; csrftoken={auth['csrf_token']}",
    }
    res = client.post(
        f"{base_url}/api/learning-paths/{path_id}/nodes/{node_id}/assessments?purpose=formal",
        headers=headers,
    )
    assert_ok(step, res)
    data = res.json()
    assessment_id = data["assessment_id"]
    active_task_id = data.get("active_task_id")

    # Poll until ready
    if active_task_id or data.get("status") != "ready":
        for attempt in range(1, MAX_POLL_RETRIES + 1):
            res = client.get(
                f"{base_url}/api/learning-paths/{path_id}/nodes/{node_id}/assessments/{assessment_id}",
                headers=headers,
            )
            assert_ok(step, res)
            a = res.json()
            status = a.get("status", "")
            log(step, f"Poll attempt {attempt}: assessment status={status}")
            if status == "ready":
                break
            if status == "failed":
                fail(step, "Assessment generation failed")
            time.sleep(POLL_INTERVAL)

    log(step, f"Assessment ready: {assessment_id}")
    return assessment_id  # type: ignore[no-any-return]


def step_submit_assessment(
    client: httpx.Client,
    base_url: str,
    auth: dict[str, str],
    path_id: str,
    node_id: str,
    assessment_id: str,
) -> dict[str, Any]:
    """Step 16: Submit assessment with answers."""
    step = "SUBMIT_ASSESSMENT"
    headers = {
        "Content-Type": "application/json",
        "X-CSRF-Token": auth["csrf_token"],
        "Cookie": f"access_token={auth['access_token']}; csrftoken={auth['csrf_token']}",
    }

    # Get assessment to read questions
    res = client.get(
        f"{base_url}/api/learning-paths/{path_id}/nodes/{node_id}/assessments/{assessment_id}",
        headers=headers,
    )
    assert_ok(step, res)
    questions = res.json().get("questions", [])

    if not questions:
        fail(step, "Assessment contains no questions")
    answers = _build_smoke_answers(questions)

    res = client.post(
        f"{base_url}/api/assessments/{assessment_id}/submit",
        json={"answers": answers},
        headers=headers,
    )
    assert_ok(step, res)
    result = res.json()
    log(step, f"Assessment submitted: status={result.get('status')}, score={result.get('score')}")
    return result  # type: ignore[no-any-return]


def step_verify_mastery_and_unlock(
    client: httpx.Client,
    base_url: str,
    auth: dict[str, str],
    path_id: str,
    node_id: str,
    submit_result: dict[str, Any],
) -> None:
    """Step 17-18: Verify mastery updated and next node unlocked."""
    step = "VERIFY_MASTERY_UNLOCK"
    headers = {
        "X-CSRF-Token": auth["csrf_token"],
        "Cookie": f"access_token={auth['access_token']}; csrftoken={auth['csrf_token']}",
    }
    if submit_result.get("active_task_id"):
        task_id = submit_result["active_task_id"]
        poll_task(client, step, task_id, headers, base_url)
        log(step, "Async grading completed")

    attempt_id = submit_result.get("attempt_id")
    if not attempt_id:
        fail(step, "Assessment submission did not return attempt_id")

    attempt: dict[str, Any] = {}
    for poll_attempt in range(1, 11):
        res = client.get(
            f"{base_url}/api/learning-paths/{path_id}/nodes/{node_id}/attempts/{attempt_id}",
            headers=headers,
        )
        assert_ok(step, res)
        attempt = res.json()
        if attempt.get("status") == "completed":
            break
        log(step, f"Attempt poll {poll_attempt}: status={attempt.get('status')}")
        time.sleep(POLL_INTERVAL)

    score = float(attempt.get("score") or 0)
    mastery_after = float(attempt.get("mastery_after") or 0)
    unlocked = attempt.get("unlocked_node_ids") or []
    log(
        step,
        f"Attempt status={attempt.get('status')}, score={score:.1f}, "
        f"mastery={mastery_after:.1f}, unlocked={len(unlocked)}",
    )
    if attempt.get("status") != "completed":
        fail(step, f"Assessment attempt did not complete: {attempt.get('status')}")
    if score < ASSESSMENT_PASS_THRESHOLD or attempt.get("assessment_passed") is not True:
        fail(step, f"Assessment did not pass: score={score:.1f}")
    if mastery_after < NODE_COMPLETION_THRESHOLD:
        fail(step, f"Mastery did not reach completion threshold: {mastery_after:.1f}")
    if attempt.get("node_completed") is not True or attempt.get("progress_status") != "completed":
        fail(step, "Node progress was not completed after passing assessment")
    if not unlocked:
        fail(step, "No successor node was unlocked")
    log(step, "Mastery update, node completion, and successor unlock verified")


def step_upload_knowledge(
    client: httpx.Client,
    base_url: str,
    auth: dict[str, str],
) -> str:
    """Step 19: Upload a knowledge document. Returns document_id."""
    step = "UPLOAD_KNOWLEDGE"
    headers = {
        "X-CSRF-Token": auth["csrf_token"],
        "Cookie": f"access_token={auth['access_token']}; csrftoken={auth['csrf_token']}",
    }

    # Create a simple text file
    file_content = b"""Python Programming Basics

Variables and Data Types
Python supports several built-in data types including integers, floats, strings, and booleans.
Variables are created by assignment and do not need explicit type declarations.

Control Flow
Python uses if, elif, and else for conditional logic.
For loops iterate over sequences, while loops repeat until a condition is met.

Functions
Functions are defined using the def keyword.
They can accept parameters and return values.
Lambda functions provide a concise way to create anonymous functions.

Data Structures
Lists are ordered, mutable sequences.
Dictionaries are key-value pairs.
Sets are unordered collections of unique elements.
Tuples are ordered, immutable sequences.
"""
    files = {
        "file": ("python_basics.txt", file_content, "text/plain"),
    }
    res = client.post(
        f"{base_url}/api/knowledge/documents",
        files=files,
        headers=headers,
    )
    assert_ok(step, res)
    data = res.json()
    document_id = data.get("document_id", "")
    task_id = data.get("index_task_id", "")
    log(step, f"Document uploaded: {document_id}, task_id={task_id}")
    return document_id  # type: ignore[no-any-return]


def step_wait_index(
    client: httpx.Client,
    base_url: str,
    auth: dict[str, str],
    document_id: str,
) -> None:
    """Step 20: Wait for knowledge indexing to complete."""
    step = "WAIT_INDEX"
    headers = {
        "X-CSRF-Token": auth["csrf_token"],
        "Cookie": f"access_token={auth['access_token']}; csrftoken={auth['csrf_token']}",
    }

    for attempt in range(1, MAX_POLL_RETRIES + 1):
        res = client.get(
            f"{base_url}/api/knowledge/documents",
            headers=headers,
        )
        assert_ok(step, res)
        docs = res.json().get("items", [])
        doc = next((d for d in docs if d.get("document_id") == document_id), None)
        if not doc:
            log(step, f"Poll attempt {attempt}: document not found in list")
            time.sleep(POLL_INTERVAL)
            continue

        status = doc.get("status", "")
        log(step, f"Poll attempt {attempt}: document status={status}")
        if status == "indexed" or status == "ready":
            log(step, "Document indexed")
            return
        if status == "failed":
            fail(step, f"Indexing failed: {doc.get('error', '')}")

        time.sleep(POLL_INTERVAL)

    fail(step, "Indexing timed out")


def step_search_knowledge(
    client: httpx.Client,
    base_url: str,
    auth: dict[str, str],
    document_id: str,
) -> None:
    """Step 21: Search the knowledge base."""
    step = "SEARCH_KNOWLEDGE"
    headers = {
        "X-CSRF-Token": auth["csrf_token"],
        "Cookie": f"access_token={auth['access_token']}; csrftoken={auth['csrf_token']}",
    }
    res = client.get(f"{base_url}/api/knowledge/search", params={"q": "Lambda", "limit": 5}, headers=headers)
    assert_ok(step, res)
    results = res.json().get("results", [])
    count = len(results)
    log(step, f"Search returned {count} results")

    if count == 0:
        fail(step, "Indexed document could not be found by exact-content search")
    if not any(result.get("document_id") == document_id for result in results):
        fail(step, "Search results did not include the document uploaded by this flow")
    log(step, "Uploaded document search hit verified")


def step_tutor(
    client: httpx.Client,
    base_url: str,
    auth: dict[str, str],
    path_id: str,
    node_id: str,
) -> None:
    """Step 22: Ask the tutor a question."""
    step = "TUTOR"
    headers = {
        "Content-Type": "application/json",
        "X-CSRF-Token": auth["csrf_token"],
        "Cookie": f"access_token={auth['access_token']}; csrftoken={auth['csrf_token']}",
    }
    res = client.post(
        f"{base_url}/api/chat",
        json={
            "question": "Python 中的变量是什么？",
            "node_id": node_id,
            "path_id": path_id,
        },
        headers=headers,
        timeout=120.0,
    )
    assert_ok(step, res)
    data = res.json()
    answer = data.get("answer", "")
    citations = data.get("citations", [])
    log(step, f"Tutor answered ({len(answer)} chars, {len(citations)} citations)")
    if not answer:
        fail(step, "Tutor returned empty answer")


def step_recommendations(
    client: httpx.Client,
    base_url: str,
    auth: dict[str, str],
    path_id: str,
) -> None:
    """Step 23: Get recommendations."""
    step = "RECOMMENDATIONS"
    headers = {
        "X-CSRF-Token": auth["csrf_token"],
        "Cookie": f"access_token={auth['access_token']}; csrftoken={auth['csrf_token']}",
    }
    res = client.get(
        f"{base_url}/api/learning-paths/{path_id}/recommendations",
        headers=headers,
    )
    assert_ok(step, res)
    items = res.json().get("items", [])
    log(step, f"Recommendations: {len(items)} items")
    # Verify no hardcoded mock
    for item in items:
        if "mock" in json.dumps(item).lower():
            fail(step, "Found hardcoded mock data in recommendations!")


def step_resume(
    client: httpx.Client,
    base_url: str,
    auth: dict[str, str],
    path_id: str,
) -> None:
    """Step 24: Verify resume state."""
    step = "RESUME"
    headers = {
        "X-CSRF-Token": auth["csrf_token"],
        "Cookie": f"access_token={auth['access_token']}; csrftoken={auth['csrf_token']}",
    }
    res = client.get(
        f"{base_url}/api/learning/resume",
        headers=headers,
    )
    assert_ok(step, res)
    data = res.json()
    resume_type = data.get("type", "")
    log(step, f"Resume type: {resume_type}")
    if resume_type not in {"active", "completed"}:
        fail(step, f"Expected active/completed resume after learning, got {resume_type!r}")
    if data.get("path_id") != path_id:
        fail(step, "Resume points to a different learning path")
    if int(data.get("completed_nodes") or 0) < 1:
        fail(step, "Resume does not report the completed first node")
    if resume_type == "active":
        if not data.get("current_node_id") or not data.get("current_node_title"):
            fail(step, "Active resume is missing the next learning node")
        if float(data.get("progress") or 0) <= 0:
            fail(step, "Active resume progress was not updated")
    log(step, "Resume state and path progress verified")


def step_verify_agent_traces(
    client: httpx.Client,
    base_url: str,
    auth: dict[str, str],
) -> None:
    """Verify that real workflow tasks expose durable multi-agent evidence."""
    step = "VERIFY_AGENT_TRACES"
    headers = {
        "X-CSRF-Token": auth["csrf_token"],
        "Cookie": f"access_token={auth['access_token']}; csrftoken={auth['csrf_token']}",
    }
    res = client.get(f"{base_url}/api/tasks", params={"limit": 50}, headers=headers)
    assert_ok(step, res)
    tasks = res.json().get("items", [])
    expected_agents = {
        "learning_path_generation": {"profile_context", "path_planner", "path_validator"},
        "learning_unit_generation": {"profile_context", "content_generator", "quality_gate", "content_reviewer"},
        "learning_lecture_generation": {"source_material_analyzer", "lecture_generator", "lecture_quality_gate"},
        "learning_assessment_generation": {
            "profile_context",
            "assessment_designer",
            "assessment_validator",
        },
    }
    for task_type, required in expected_agents.items():
        task = next((item for item in tasks if item.get("type") == task_type), None)
        if not task:
            fail(step, f"Missing completed workflow task: {task_type}")
        trace = task.get("agent_trace") or []
        actual = {item.get("agent_key") for item in trace}
        missing = required - actual
        if missing:
            fail(step, f"Task {task_type} is missing agent trace steps: {sorted(missing)}")
        if any(item.get("status") == "running" for item in trace):
            fail(step, f"Task {task_type} left running agent trace steps after completion")
        log(step, f"{task_type}: {len(trace)} trace steps verified")

    log(step, "Multi-agent collaboration evidence verified")


def step_logout(
    client: httpx.Client,
    base_url: str,
    auth: dict[str, str],
) -> None:
    """Step 25: Logout."""
    step = "LOGOUT"
    headers = {
        "X-CSRF-Token": auth["csrf_token"],
        "Cookie": f"access_token={auth['access_token']}; csrftoken={auth['csrf_token']}",
    }
    res = client.post(
        f"{base_url}/api/auth/logout",
        headers=headers,
    )
    assert_ok(step, res)
    log(step, "Logout successful")


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────


def main() -> int:
    # Windows terminals may default to GBK, which cannot render the status
    # symbols used by this script and used to hide the original API failure.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="EduAgentX Full Learning Flow Smoke Test")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Backend base URL (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Total timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    print(f"\n{'=' * 60}")
    print("EduAgentX Full Learning Flow Smoke Test")
    print(f"Backend: {base_url}")
    print(f"Timeout: {args.timeout}s")
    print(f"{'=' * 60}\n")

    start_time = time.time()

    try:
        with httpx.Client(timeout=120.0) as client:
            # 1. Register
            print("\n── Step 1: Register ──")
            reg = step_register(client, base_url)

            # 2. Login
            print("\n── Step 2: Login ──")
            auth = step_login(client, base_url, reg["email"], reg["password"])
            auth["user_id"] = reg["user_id"]

            # 3. Onboarding
            print("\n── Step 3: Onboarding ──")
            step_onboarding(client, base_url, auth)

            # 4. Create Goal
            print("\n── Step 4: Create Goal ──")
            goal_id = step_create_goal(client, base_url, auth)

            # 5. Clarification
            print("\n── Step 5: Clarification ──")
            step_clarification(client, base_url, auth, goal_id)

            # 6. Diagnostic
            print("\n── Step 6: Diagnostic ──")
            step_diagnostic(client, base_url, auth, goal_id)

            # 7. Wait for Diagnostic Grading + Path Generation
            print("\n── Step 7: Wait for Diagnostic Grading ──")
            step_wait_diagnostic_grading(client, base_url, auth, goal_id)

            # 8. Get Path
            print("\n── Step 8: Get Learning Path ──")
            path_info = step_get_path(client, base_url, auth, goal_id)
            path_id = path_info["path_id"]

            # 9. Request Path Revision
            print("\n── Step 9: Request Path Revision ──")
            revision_task_id = step_request_revision(client, base_url, auth, path_id)

            # 10. Wait for Revision
            print("\n── Step 10: Wait for Revision ──")
            step_wait_revision(client, base_url, auth, revision_task_id)

            # 11. Activate Version
            print("\n── Step 11: Activate Version ──")
            step_activate_version(client, base_url, auth, path_id)

            # 12. Generate Unit Content
            print("\n── Step 12: Generate Unit Content ──")
            node_id = step_generate_unit(client, base_url, auth, path_id)

            # 13. Generate Lecture
            print("\n── Step 13: Generate Lecture ──")
            step_generate_lecture(client, base_url, auth, path_id, node_id)

            # 14. Generate Practice
            print("\n── Step 14: Generate Practice ──")
            step_generate_practice(client, base_url, auth, path_id, node_id)

            # 15. Generate Assessment
            print("\n── Step 15: Generate Assessment ──")
            assessment_id = step_generate_assessment(client, base_url, auth, path_id, node_id)

            # 16. Submit Assessment
            print("\n── Step 16: Submit Assessment ──")
            submit_result = step_submit_assessment(client, base_url, auth, path_id, node_id, assessment_id)

            # 17-18. Verify Mastery and Unlock
            print("\n── Step 17-18: Verify Mastery & Node Unlock ──")
            step_verify_mastery_and_unlock(client, base_url, auth, path_id, node_id, submit_result)

            # 19. Upload Knowledge Document
            print("\n── Step 19: Upload Knowledge Document ──")
            document_id = step_upload_knowledge(client, base_url, auth)

            # 20. Wait for Index
            print("\n── Step 20: Wait for Index ──")
            step_wait_index(client, base_url, auth, document_id)

            # 21. Search Knowledge
            print("\n── Step 21: Search Knowledge ──")
            step_search_knowledge(client, base_url, auth, document_id)

            # 22. Tutor Q&A
            print("\n── Step 22: Tutor Q&A ──")
            step_tutor(client, base_url, auth, path_id, node_id)

            # 23. Recommendations
            print("\n── Step 23: Get Recommendations ──")
            step_recommendations(client, base_url, auth, path_id)

            # 24. Verify Multi-Agent Trace
            print("\n── Step 24: Verify Multi-Agent Trace ──")
            step_verify_agent_traces(client, base_url, auth)

            # 25. Verify Resume
            print("\n── Step 25: Verify Resume ──")
            step_resume(client, base_url, auth, path_id)

            # 26. Logout
            print("\n── Step 26: Logout ──")
            step_logout(client, base_url, auth)

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"\n❌ FAILED after {elapsed:.1f}s")
        if isinstance(e, SystemExit):
            raise
        print(f"   Unexpected error: {type(e).__name__}: {e}")
        sys.exit(1)

    elapsed = time.time() - start_time
    print(f"\n{'=' * 60}")
    print("FULL LEARNING FLOW PASSED")
    print(f"Total time: {elapsed:.1f}s")
    print(f"{'=' * 60}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
