"""E2E test-only API routes.

These routes are ONLY registered when:
  - APP_ENV == "test"
  - ENABLE_E2E_ROUTES == "true"

They require the X-E2E-Token header to match E2E_TOKEN.
They refuse to run against non-test databases.
They are excluded from OpenAPI schema (include_in_schema=False).
"""

from __future__ import annotations

import hmac
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.datetime import utc_now
from app.core.database import get_db
from app.core.errors import ApiError
from app.models.goal import LearningGoal
from app.models.outbox import OutboxEvent
from app.models.path import (
    LearningEdge,
    LearningNode,
    LearningPath,
    LearningPathVersion,
    LearningStage,
)
from app.models.task import BackgroundTask, TaskEvent
from app.models.user import AuthSession, User

router = APIRouter(prefix="/api/__e2e__", tags=["e2e"], include_in_schema=False)


def _require_e2e_token(x_e2e_token: str = Header(...)) -> None:
    """Validate the E2E test token using constant-time comparison."""
    from app.config import get_settings

    settings = get_settings()
    expected = settings.e2e_token
    if not expected or not hmac.compare_digest(x_e2e_token, expected):
        raise ApiError(code="FORBIDDEN", message="Invalid E2E token", status_code=403)


async def _require_test_db(db: AsyncSession = Depends(get_db)) -> None:
    """Ensure we are running against a test database, not production."""
    from sqlalchemy.engine import make_url

    from app.config import get_settings

    settings = get_settings()
    database_name = make_url(settings.database_url).database

    if not database_name:
        raise ApiError(code="FORBIDDEN", message="Database name is missing", status_code=403)

    if not database_name.endswith(("_test", "_e2e")):
        raise ApiError(
            code="FORBIDDEN",
            message=f"E2E routes require a test-only database, got '{database_name}'",
            status_code=403,
        )


@router.post("/bootstrap-learning-session")
async def bootstrap_learning_session(
    request: Request,
    _token: None = Depends(_require_e2e_token),
    _db_check: None = Depends(_require_test_db),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Create a fully-authenticated user with onboarding completed.

    Returns JSON with auth tokens and sets CSRF cookie.
    The caller can use these tokens directly in subsequent API calls.
    """
    from app.config import get_settings
    from app.core.security import (
        create_access_token,
        generate_csrf_token,
        generate_jti,
        generate_token,
        hash_password,
        hash_token,
    )

    uid = str(uuid.uuid4())[:8]
    email = f"e2e-bootstrap-{uid}@example.com"
    password = "E2E-Bootstrap-Pass-123!"
    now = utc_now()

    # Create user
    user = User(
        id=str(uuid.uuid4()),
        email=email,
        email_normalized=email.lower(),
        display_name=f"E2E User {uid}",
        password_hash=hash_password(password),
        status="active",
        email_verified_at=now,
        onboarding_completed_at=now,
    )
    db.add(user)
    await db.flush()

    # Create session
    jti = generate_jti()
    family_id = str(uuid.uuid4())
    refresh_token = generate_token()

    session = AuthSession(
        id=str(uuid.uuid4()),
        user_id=user.id,
        refresh_token_hash=hash_token(refresh_token),
        refresh_token_jti=jti,
        token_family_id=family_id,
        user_agent="e2e-test",
        ip_address="127.0.0.1",
        expires_at=utc_now().replace(year=utc_now().year + 1),
    )
    db.add(session)
    await db.flush()
    await db.commit()

    access_token = create_access_token(user.id, session.id)
    csrf_token = generate_csrf_token()
    settings = get_settings()

    response = JSONResponse(
        content={
            "user_id": user.id,
            "email": email,
            "password": password,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "csrf_token": csrf_token,
            "session_id": session.id,
        },
    )
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        httponly=False,
        samesite="lax",
        secure=False,
    )
    return response


@router.post("/create-progress-task")
async def create_progress_task(
    request: Request,
    _token: None = Depends(_require_e2e_token),
    _db_check: None = Depends(_require_test_db),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a deterministic background task that progresses through states.

    The task goes through: pending → running → progress → completed
    using real PostgreSQL, Outbox, Task Events, and Redis Pub/Sub.

    Returns: { task_id }
    """
    task_id = str(uuid.uuid4())
    user_id = request.headers.get("X-E2E-User-Id", "")

    if not user_id:
        raise ApiError(code="BAD_REQUEST", message="X-E2E-User-Id required", status_code=400)

    # Create task
    task = BackgroundTask(
        id=task_id,
        user_id=user_id,
        task_type="e2e_progress_test",
        status="pending",
        target_type="e2e",
        target_id=task_id,
        expires_at=utc_now().replace(hour=utc_now().hour + 1),
    )
    db.add(task)

    # Create initial event
    event = TaskEvent(
        id=str(uuid.uuid4()),
        task_id=task_id,
        sequence_number=0,
        event_type="snapshot",
        status="pending",
        progress=0,
        message="E2E task created",
    )
    db.add(event)

    # Create outbox event for worker pickup
    outbox = OutboxEvent(
        id=str(uuid.uuid4()),
        event_type="task.execute",
        aggregate_type="BackgroundTask",
        aggregate_id=task_id,
        payload={"task_id": task_id, "task_type": "e2e_progress_test"},
        status="pending",
    )
    db.add(outbox)

    await db.commit()

    return {"task_id": task_id}


@router.post("/bootstrap-path-version")
async def bootstrap_path_version(
    request: Request,
    _token: None = Depends(_require_e2e_token),
    _db_check: None = Depends(_require_test_db),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a learning path with an active version for revision E2E tests.

    Creates: LearningGoal → LearningPath → LearningPathVersion (active)
             → LearningStage (2) → LearningNode (4) → LearningEdge (3)

    Returns: { path_id, version_id, goal_id }
    Requires X-E2E-User-Id header with the user_id from bootstrap-learning-session.
    """
    user_id = request.headers.get("X-E2E-User-Id", "")
    if not user_id:
        raise ApiError(code="BAD_REQUEST", message="X-E2E-User-Id required", status_code=400)

    now = utc_now()
    goal_id = str(uuid.uuid4())
    path_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())

    # LearningGoal
    goal = LearningGoal(
        id=goal_id,
        user_id=user_id,
        title="E2E Path Revision Test Goal",
        raw_description="Test learning goal for path revision E2E",
        use_diagnostic=False,
    )
    db.add(goal)

    # LearningPath (without active_version_id initially — circular FK)
    path = LearningPath(
        id=path_id,
        user_id=user_id,
        goal_id=goal_id,
        status="active",
    )
    db.add(path)
    await db.flush()

    # LearningPathVersion (active)
    version = LearningPathVersion(
        id=version_id,
        path_id=path_id,
        version_number=1,
        source="initial_generation",
        status="active",
        summary="E2E test path version 1",
        estimated_total_minutes=120,
        created_by="system",
        activated_at=now,
    )
    db.add(version)
    await db.flush()

    # Now set the path's active_version_id
    path.active_version_id = version_id

    # LearningStage (2 stages)
    stage1_id = str(uuid.uuid4())
    stage1 = LearningStage(
        id=stage1_id,
        version_id=version_id,
        title="基础概念",
        description="Foundation concepts",
        stage_order=1,
    )
    db.add(stage1)

    stage2_id = str(uuid.uuid4())
    stage2 = LearningStage(
        id=stage2_id,
        version_id=version_id,
        title="进阶应用",
        description="Advanced applications",
        stage_order=2,
    )
    db.add(stage2)
    await db.flush()

    # LearningNode (4 nodes with logical_keys for progress migration)
    nodes = [
        LearningNode(
            id=str(uuid.uuid4()),
            version_id=version_id,
            stage_id=stage1_id,
            logical_key="e2e-concept-1",
            title="概念一",
            description="E2E test concept 1",
            node_order=1,
            level=1,
            difficulty="beginner",
            estimated_minutes=30,
            status="unlocked",
            content_status="not_generated",
        ),
        LearningNode(
            id=str(uuid.uuid4()),
            version_id=version_id,
            stage_id=stage1_id,
            logical_key="e2e-concept-2",
            title="概念二",
            description="E2E test concept 2",
            node_order=2,
            level=1,
            difficulty="beginner",
            estimated_minutes=30,
            status="locked",
            content_status="not_generated",
        ),
        LearningNode(
            id=str(uuid.uuid4()),
            version_id=version_id,
            stage_id=stage2_id,
            logical_key="e2e-advanced-1",
            title="进阶一",
            description="E2E test advanced 1",
            node_order=3,
            level=2,
            difficulty="intermediate",
            estimated_minutes=30,
            status="locked",
            content_status="not_generated",
        ),
        LearningNode(
            id=str(uuid.uuid4()),
            version_id=version_id,
            stage_id=stage2_id,
            logical_key="e2e-advanced-2",
            title="进阶二",
            description="E2E test advanced 2",
            node_order=4,
            level=2,
            difficulty="intermediate",
            estimated_minutes=30,
            status="locked",
            content_status="not_generated",
        ),
    ]
    for n in nodes:
        db.add(n)
    await db.flush()

    # LearningEdge (3 prerequisite edges)
    edges = [
        LearningEdge(
            id=str(uuid.uuid4()),
            version_id=version_id,
            source_node_id=nodes[0].id,
            target_node_id=nodes[1].id,
        ),
        LearningEdge(
            id=str(uuid.uuid4()),
            version_id=version_id,
            source_node_id=nodes[1].id,
            target_node_id=nodes[2].id,
        ),
        LearningEdge(
            id=str(uuid.uuid4()),
            version_id=version_id,
            source_node_id=nodes[2].id,
            target_node_id=nodes[3].id,
        ),
    ]
    for e in edges:
        db.add(e)

    await db.commit()

    return {
        "path_id": path_id,
        "version_id": version_id,
        "goal_id": goal_id,
    }


# ---------------------------------------------------------------------------
# Assessment E2E helpers
# ---------------------------------------------------------------------------


@router.post("/bootstrap-assessment")
async def bootstrap_assessment(
    request: Request,
    _token: None = Depends(_require_e2e_token),
    _db_check: None = Depends(_require_test_db),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a path + ready objective-only assessment for E2E tests.

    Creates: LearningGoal → LearningPath → LearningPathVersion (active)
             → LearningStage (1) → LearningNode (3) → LearningEdge (2)
             → Assessment (ready) → AssessmentQuestion (5, objective only)

    Returns: { path_id, version_id, node_ids, assessment_id, correct_answers }
    """
    import json

    from app.models.unit import Assessment, AssessmentQuestion

    user_id = request.headers.get("X-E2E-User-Id", "")
    if not user_id:
        raise ApiError(code="BAD_REQUEST", message="X-E2E-User-Id required", status_code=400)

    now = utc_now()
    goal_id = str(uuid.uuid4())
    path_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())

    # LearningGoal
    goal = LearningGoal(
        id=goal_id,
        user_id=user_id,
        title="E2E Assessment Test Goal",
        raw_description="Test learning goal for assessment E2E",
        use_diagnostic=False,
    )
    db.add(goal)

    # LearningPath
    path = LearningPath(
        id=path_id,
        user_id=user_id,
        goal_id=goal_id,
        status="active",
    )
    db.add(path)
    await db.flush()

    # LearningPathVersion (active)
    version = LearningPathVersion(
        id=version_id,
        path_id=path_id,
        version_number=1,
        source="initial_generation",
        status="active",
        summary="E2E test path for assessment",
        estimated_total_minutes=90,
        created_by="system",
        activated_at=now,
    )
    db.add(version)
    await db.flush()

    path.active_version_id = version_id

    # LearningStage (1 stage)
    stage_id = str(uuid.uuid4())
    stage = LearningStage(
        id=stage_id,
        version_id=version_id,
        title="核心概念",
        description="Core concepts",
        stage_order=1,
    )
    db.add(stage)
    await db.flush()

    # LearningNode (3 nodes: A → B → C)
    node_a_id = str(uuid.uuid4())
    node_b_id = str(uuid.uuid4())
    node_c_id = str(uuid.uuid4())

    nodes = [
        LearningNode(
            id=node_a_id,
            version_id=version_id,
            stage_id=stage_id,
            logical_key="e2e-assess-node-a",
            title="评估节点A",
            description="E2E assessment node A",
            node_order=1,
            level=1,
            difficulty="beginner",
            estimated_minutes=30,
            status="unlocked",
            content_status="not_generated",
        ),
        LearningNode(
            id=node_b_id,
            version_id=version_id,
            stage_id=stage_id,
            logical_key="e2e-assess-node-b",
            title="评估节点B",
            description="E2E assessment node B",
            node_order=2,
            level=1,
            difficulty="intermediate",
            estimated_minutes=30,
            status="locked",
            content_status="not_generated",
        ),
        LearningNode(
            id=node_c_id,
            version_id=version_id,
            stage_id=stage_id,
            logical_key="e2e-assess-node-c",
            title="评估节点C",
            description="E2E assessment node C",
            node_order=3,
            level=2,
            difficulty="intermediate",
            estimated_minutes=30,
            status="locked",
            content_status="not_generated",
        ),
    ]
    for n in nodes:
        db.add(n)
    await db.flush()

    # LearningEdge: A → B, B → C
    edges = [
        LearningEdge(
            id=str(uuid.uuid4()),
            version_id=version_id,
            source_node_id=node_a_id,
            target_node_id=node_b_id,
        ),
        LearningEdge(
            id=str(uuid.uuid4()),
            version_id=version_id,
            source_node_id=node_b_id,
            target_node_id=node_c_id,
        ),
    ]
    for e in edges:
        db.add(e)

    # Create ready Assessment with only objective questions
    assessment_id = str(uuid.uuid4())
    assessment = Assessment(
        id=assessment_id,
        user_id=user_id,
        path_id=path_id,
        path_version_id=version_id,
        node_id=node_a_id,
        purpose="formal",
        status="ready",
    )
    db.add(assessment)
    await db.flush()

    # 5 objective questions with known correct answers
    # Q1: single_choice (correct: "a", max_score: 1)
    # Q2: single_choice (correct: "b", max_score: 1)
    # Q3: multiple_choice (correct: ["a", "b"], max_score: 2)
    # Q4: true_false (correct: false, max_score: 1)
    # Q5: single_choice (correct: "c", max_score: 1)
    # Total: 6 points

    questions_data: list[dict[str, Any]] = [
        {
            "type": "single_choice",
            "prompt": "E2E测试：以下哪个是正确的基本概念描述？",
            "options": json.dumps(
                [
                    {"value": "a", "label": "正确的概念描述"},
                    {"value": "b", "label": "错误的概念描述"},
                    {"value": "c", "label": "不相关的描述"},
                    {"value": "d", "label": "完全错误的描述"},
                ]
            ),
            "correct_answer": json.dumps("a"),
            "max_score": 1.0,
        },
        {
            "type": "single_choice",
            "prompt": "E2E测试：以下哪个选项最准确？",
            "options": json.dumps(
                [
                    {"value": "a", "label": "不准确的选项"},
                    {"value": "b", "label": "最准确的选项"},
                    {"value": "c", "label": "部分正确的选项"},
                    {"value": "d", "label": "完全错误的选项"},
                ]
            ),
            "correct_answer": json.dumps("b"),
            "max_score": 1.0,
        },
        {
            "type": "multiple_choice",
            "prompt": "E2E测试：以下哪些是正确的？（多选）",
            "options": json.dumps(
                [
                    {"value": "a", "label": "正确的选项A"},
                    {"value": "b", "label": "正确的选项B"},
                    {"value": "c", "label": "错误的选项C"},
                    {"value": "d", "label": "错误的选项D"},
                ]
            ),
            "correct_answer": json.dumps(["a", "b"]),
            "max_score": 2.0,
        },
        {
            "type": "true_false",
            "prompt": "E2E测试：理论与实践相结合是高效的学习方式。",
            "options": None,
            "correct_answer": json.dumps(False),
            "max_score": 1.0,
        },
        {
            "type": "single_choice",
            "prompt": "E2E测试：遇到问题时应采取什么策略？",
            "options": json.dumps(
                [
                    {"value": "a", "label": "直接重写所有代码"},
                    {"value": "b", "label": "忽略错误信息"},
                    {"value": "c", "label": "系统性排查并定位问题"},
                    {"value": "d", "label": "等待他人帮助"},
                ]
            ),
            "correct_answer": json.dumps("c"),
            "max_score": 1.0,
        },
    ]

    correct_answers: dict[str, Any] = {}
    for idx, q_data in enumerate(questions_data):
        q_id = str(uuid.uuid4())
        aq = AssessmentQuestion(
            id=q_id,
            assessment_id=assessment_id,
            question_type=q_data["type"],
            prompt=q_data["prompt"],
            options=q_data["options"],
            correct_answer=q_data["correct_answer"],
            difficulty="easy" if idx < 2 else "medium",
            knowledge_point=f"E2E测试知识点{idx + 1}",
            explanation=f"E2E测试题目{idx + 1}的解析",
            points=int(q_data["max_score"]),
            max_score=q_data["max_score"],
            question_order=idx + 1,
        )
        db.add(aq)

        # Build correct_answers for the response
        parsed = json.loads(q_data["correct_answer"])
        if q_data["type"] == "true_false":
            correct_answers[q_id] = bool(parsed)
        elif q_data["type"] == "multiple_choice":
            correct_answers[q_id] = list(parsed)
        else:
            correct_answers[q_id] = str(parsed)

    await db.commit()

    return {
        "path_id": path_id,
        "version_id": version_id,
        "node_ids": [node_a_id, node_b_id, node_c_id],
        "assessment_id": assessment_id,
        "correct_answers": correct_answers,
    }


@router.get("/assessment-answers/{assessment_id}")
async def get_assessment_answers(
    assessment_id: str,
    _token: None = Depends(_require_e2e_token),
    _db_check: None = Depends(_require_test_db),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return correct answers for an assessment (E2E test only).

    Parses the stored correct_answer JSON strings into native types:
    - single_choice → str
    - multiple_choice → list[str]
    - true_false → bool
    - short_answer → None (no deterministic correct answer)
    """
    import json

    from app.models.unit import AssessmentQuestion

    result = await db.execute(
        select(AssessmentQuestion)
        .where(AssessmentQuestion.assessment_id == assessment_id)
        .order_by(AssessmentQuestion.question_order)
    )
    questions = list(result.scalars().all())

    if not questions:
        raise ApiError(code="NOT_FOUND", message="Assessment has no questions", status_code=404)

    answers: dict[str, Any] = {}
    for q in questions:
        if q.question_type == "short_answer":
            answers[q.id] = None
            continue
        if not q.correct_answer:
            answers[q.id] = None
            continue
        try:
            parsed = json.loads(q.correct_answer)
        except (json.JSONDecodeError, TypeError):
            answers[q.id] = q.correct_answer
            continue
        if q.question_type == "true_false":
            answers[q.id] = bool(parsed)
        elif q.question_type == "multiple_choice":
            answers[q.id] = list(parsed) if isinstance(parsed, list) else [str(parsed)]
        else:
            answers[q.id] = str(parsed)

    return {"assessment_id": assessment_id, "correct_answers": answers}


# ---------------------------------------------------------------------------
# Profile E2E helpers
# ---------------------------------------------------------------------------


@router.post("/bootstrap-profile-user")
async def bootstrap_profile_user(
    request: Request,
    _token: None = Depends(_require_e2e_token),
    _db_check: None = Depends(_require_test_db),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Create a fully-authenticated user for profile E2E tests.

    Unlike ``bootstrap-learning-session``, this endpoint:
      - Does NOT create any goal, path, or assessment
      - Does NOT create a StudentProfile (the E2E test must use real
        conversation → finalize to build one)
      - Returns auth tokens so the browser can interact directly

    The caller is expected to drive the profile conversation, finalize,
    and verification entirely through real API code paths.
    """
    from app.config import get_settings
    from app.core.security import (
        create_access_token,
        generate_csrf_token,
        generate_jti,
        generate_token,
        hash_password,
        hash_token,
    )

    uid = str(uuid.uuid4())[:8]
    email = f"e2e-profile-{uid}@example.com"
    password = "E2E-Profile-Pass-123!"
    now = utc_now()

    user = User(
        id=str(uuid.uuid4()),
        email=email,
        email_normalized=email.lower(),
        display_name=f"E2E Profile User {uid}",
        password_hash=hash_password(password),
        status="active",
        email_verified_at=now,
        onboarding_completed_at=now,
    )
    db.add(user)
    await db.flush()

    jti = generate_jti()
    family_id = str(uuid.uuid4())
    refresh_token = generate_token()

    session = AuthSession(
        id=str(uuid.uuid4()),
        user_id=user.id,
        refresh_token_hash=hash_token(refresh_token),
        refresh_token_jti=jti,
        token_family_id=family_id,
        user_agent="e2e-profile-test",
        ip_address="127.0.0.1",
        expires_at=utc_now().replace(year=utc_now().year + 1),
    )
    db.add(session)
    await db.flush()
    await db.commit()

    access_token = create_access_token(user.id, session.id)
    csrf_token = generate_csrf_token()
    settings = get_settings()

    response = JSONResponse(
        content={
            "user_id": user.id,
            "email": email,
            "password": password,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "csrf_token": csrf_token,
            "session_id": session.id,
        },
    )
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        httponly=False,
        samesite="lax",
        secure=False,
    )
    return response


# ---------------------------------------------------------------------------
# Knowledge + Tutor E2E bootstrap
# ---------------------------------------------------------------------------


@router.post("/bootstrap-knowledge")
async def bootstrap_knowledge(
    request: Request,
    _token: None = Depends(_require_e2e_token),
    _db_check: None = Depends(_require_test_db),
    db: AsyncSession = Depends(get_db),
    x_e2e_user_id: str = Header(..., alias="X-E2E-User-Id"),
) -> JSONResponse:
    """Create a ready knowledge document with chunks for RAG testing."""
    from app.services.knowledge import KnowledgeService
    from app.services.storage import InMemoryObjectStorage
    from app.workers.tasks import _execute_knowledge_index

    storage = InMemoryObjectStorage()
    content = b"""
    Python Programming Fundamentals

    Python is a high-level, interpreted programming language known for its
    readability and simplicity. It supports multiple programming paradigms
    including procedural, object-oriented, and functional programming.

    Key concepts:
    - Variables and data types (int, float, str, list, dict, tuple, set)
    - Control flow (if, for, while, break, continue)
    - Functions (def, lambda, *args, **kwargs)
    - Classes and objects (class, __init__, self, inheritance)
    - Modules and packages (import, from...import)
    - Exception handling (try, except, finally, raise)

    Python's design philosophy emphasizes code readability with its notable
    use of significant indentation.
    """

    storage_key = f"knowledge/{x_e2e_user_id}/{uuid.uuid4()}_python_fundamentals.txt"
    await storage.put(storage_key, content, "text/plain")

    service = KnowledgeService(db, storage=storage)
    doc = await service.create_document(
        user_id=x_e2e_user_id,
        title="Python Fundamentals",
        filename="python_fundamentals.txt",
        mime_type="text/plain",
        size_bytes=len(content),
        storage_key=storage_key,
    )
    await db.commit()

    task = BackgroundTask(
        id=str(uuid.uuid4()),
        user_id=x_e2e_user_id,
        task_type="knowledge_index",
        target_type="document",
        target_id=doc.id,
        status="pending",
    )
    db.add(task)
    await db.commit()

    import app.services.storage as storage_mod

    original_get = storage_mod.get_object_storage
    storage_mod.get_object_storage = lambda: storage

    try:
        await _execute_knowledge_index(db, task)
    finally:
        storage_mod.get_object_storage = original_get

    return JSONResponse(
        content={
            "document_id": doc.id,
            "title": "Python Fundamentals",
            "status": "ready",
            "storage_key": storage_key,
            "content_preview": content.decode()[:200],
        }
    )


@router.post("/bootstrap-tutor-session")
async def bootstrap_tutor_session(
    request: Request,
    _token: None = Depends(_require_e2e_token),
    _db_check: None = Depends(_require_test_db),
    db: AsyncSession = Depends(get_db),
    x_e2e_user_id: str = Header(..., alias="X-E2E-User-Id"),
) -> JSONResponse:
    """Bootstrap a full tutor session: path + version + node + unit content + knowledge.

    Creates a minimal learning path with one unlocked node, unit content,
    and a ready knowledge document — everything needed to call /api/chat.
    """
    now = utc_now()
    goal_id = str(uuid.uuid4())
    path_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    node_id = str(uuid.uuid4())
    stage_id = str(uuid.uuid4())

    # LearningGoal
    goal = LearningGoal(
        id=goal_id,
        user_id=x_e2e_user_id,
        title="E2E Tutor Test Goal",
        raw_description="Test learning goal for tutor RAG E2E",
        use_diagnostic=False,
    )
    db.add(goal)

    # LearningPath
    path = LearningPath(
        id=path_id,
        user_id=x_e2e_user_id,
        goal_id=goal_id,
        status="active",
    )
    db.add(path)
    await db.flush()

    # LearningPathVersion
    version = LearningPathVersion(
        id=version_id,
        path_id=path_id,
        version_number=1,
        source="initial_generation",
        status="active",
        summary="E2E tutor test path",
        estimated_total_minutes=60,
        created_by="system",
        activated_at=now,
    )
    db.add(version)
    await db.flush()
    path.active_version_id = version_id

    # LearningStage
    stage = LearningStage(
        id=stage_id,
        version_id=version_id,
        title="Python基础",
        description="Foundation",
        stage_order=1,
    )
    db.add(stage)
    await db.flush()

    # LearningNode (1 unlocked node)
    node = LearningNode(
        id=node_id,
        version_id=version_id,
        stage_id=stage_id,
        logical_key="e2e-tutor-node-1",
        title="Python编程基础",
        description="E2E tutor test node",
        node_order=1,
        level=1,
        difficulty="beginner",
        estimated_minutes=30,
        status="unlocked",
        content_status="generated",
    )
    db.add(node)
    await db.commit()

    # Create unit content for the node
    from app.models.unit import LearningUnitContent

    unit_content = LearningUnitContent(
        id=str(uuid.uuid4()),
        path_id=path_id,
        node_id=node_id,
        user_id=x_e2e_user_id,
        content={
            "sections": [
                {
                    "title": "Python Basics",
                    "content": "Python is a versatile programming language used for web development, data science, and automation.",
                },
            ],
            "summary": "Introduction to Python programming fundamentals.",
        },
        status="ready",
    )
    db.add(unit_content)
    await db.commit()

    # Bootstrap knowledge document
    from app.services.knowledge import KnowledgeService
    from app.services.storage import InMemoryObjectStorage
    from app.workers.tasks import _execute_knowledge_index

    storage = InMemoryObjectStorage()
    content_bytes = b"""
    Python Programming Fundamentals

    Python is a high-level, interpreted programming language known for its
    readability and simplicity. It supports multiple programming paradigms
    including procedural, object-oriented, and functional programming.

    Key concepts include variables, data types, control flow, functions,
    classes, modules, and exception handling.

    Python's design philosophy emphasizes code readability with its notable
    use of significant indentation.
    """

    storage_key = f"knowledge/{x_e2e_user_id}/{uuid.uuid4()}_python_fundamentals.txt"
    await storage.put(storage_key, content_bytes, "text/plain")

    service = KnowledgeService(db, storage=storage)
    doc = await service.create_document(
        user_id=x_e2e_user_id,
        title="Python Fundamentals",
        filename="python_fundamentals.txt",
        mime_type="text/plain",
        size_bytes=len(content_bytes),
        storage_key=storage_key,
    )
    await db.commit()

    task = BackgroundTask(
        id=str(uuid.uuid4()),
        user_id=x_e2e_user_id,
        task_type="knowledge_index",
        target_type="document",
        target_id=doc.id,
        status="pending",
    )
    db.add(task)
    await db.commit()

    import app.services.storage as storage_mod

    original_get = storage_mod.get_object_storage
    storage_mod.get_object_storage = lambda: storage

    try:
        await _execute_knowledge_index(db, task)
    finally:
        storage_mod.get_object_storage = original_get

    return JSONResponse(
        content={
            "path_id": path_id,
            "version_id": version_id,
            "node_id": node_id,
            "document_id": doc.id,
            "knowledge_status": "ready",
        }
    )
