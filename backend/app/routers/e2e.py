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
    from app.core.security import (
        create_access_token,
        generate_csrf_token,
        generate_jti,
        generate_token,
        hash_password,
        hash_token,
    )

    from app.config import get_settings

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
