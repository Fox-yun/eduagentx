"""FastAPI application entry point."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.common.schemas import HealthResponse
from app.config import get_settings
from app.core.csrf import CSRFMiddleware
from app.core.database import check_database_connection, get_engine
from app.core.errors import register_error_handlers
from app.core.redis import check_redis_connection
from app.core.request_context import RequestIDMiddleware
from app.lifespan import lifespan


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="EduAgentX API",
        version="4.1.0",
        description="EduAgentX Backend",
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
    )

    # Middleware (order matters: last added = first executed)
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Error handlers
    register_error_handlers(app)

    # Health endpoints
    @app.get("/health/live", response_model=HealthResponse, tags=["health"])
    async def health_live() -> HealthResponse:
        """Liveness probe - checks if the process is running."""
        return HealthResponse(
            status="ok",
            service="eduagentx-api",
            version="4.1.0",
            api_version="4.1",
            environment=settings.app_env,
        )

    @app.get("/health/ready", tags=["health"])
    async def health_ready() -> dict[str, Any]:
        """Readiness probe - checks if the service is ready to accept requests."""
        db_ok = await check_database_connection()
        redis_ok = await check_redis_connection()

        # Check MinIO connectivity
        minio_ok = False
        try:
            from app.services.storage import get_object_storage

            storage = get_object_storage()
            minio_ok = await storage.exists("__health_check__")
            minio_ok = True  # exists() returns False for non-existent key, which means connection works
        except Exception:
            minio_ok = False

        # Check current Alembic migration version
        migration_version = None
        if db_ok:
            try:
                from sqlalchemy import text

                engine = get_engine()
                async with engine.connect() as conn:
                    result = await conn.execute(text("SELECT version_num FROM alembic_version"))
                    row = result.fetchone()
                    migration_version = row[0] if row else None
            except Exception:
                migration_version = None

        if db_ok and redis_ok and minio_ok:
            return {
                "status": "ready",
                "service": "eduagentx-api",
                "version": "4.1.0",
                "api_version": "4.1",
                "database": True,
                "redis": True,
                "minio": True,
                "migration_version": migration_version,
            }

        from fastapi import HTTPException

        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "service": "eduagentx-api",
                "database": db_ok,
                "redis": redis_ok,
                "minio": minio_ok,
                "migration_version": migration_version,
            },
        )

    # Include routers
    from app.routers.auth import router as auth_router
    from app.routers.chat import router as chat_router
    from app.routers.clarifications import router as clarifications_router
    from app.routers.diagnostics import router as diagnostics_router
    from app.routers.goals import router as goals_router
    from app.routers.knowledge import router as knowledge_router
    from app.routers.learning import router as learning_router
    from app.routers.paths import router as paths_router
    from app.routers.profile import router as profile_router
    from app.routers.resume import router as resume_router
    from app.routers.tasks import router as tasks_router
    from app.routers.units import router as units_router
    from app.routers.users import router as users_router

    app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
    app.include_router(users_router, prefix="/api/users", tags=["users"])
    app.include_router(goals_router, prefix="/api/learning-goals", tags=["goals"])
    app.include_router(clarifications_router, prefix="/api/learning-goals", tags=["clarifications"])
    app.include_router(diagnostics_router, prefix="/api/learning-goals", tags=["diagnostics"])
    app.include_router(resume_router, prefix="/api/learning/resume", tags=["resume"])
    app.include_router(tasks_router, prefix="/api/tasks", tags=["tasks"])
    app.include_router(paths_router, prefix="/api/learning-paths", tags=["paths"])
    app.include_router(units_router, prefix="/api/learning-paths", tags=["units"])
    app.include_router(chat_router, prefix="/api/chat", tags=["chat"])
    app.include_router(profile_router, prefix="/api/profile", tags=["profile"])
    app.include_router(learning_router, prefix="/api/learning", tags=["learning"])

    # Assessment submit uses a different prefix than other unit routes
    from app.routers.units import submit_assessment

    app.add_api_route(
        "/api/assessments/{assessment_id}/submit",
        submit_assessment,
        methods=["POST"],
        tags=["units"],
    )

    app.include_router(knowledge_router, prefix="/api/knowledge", tags=["knowledge"])

    # E2E test routes — only with explicit opt-in via Settings AND test environment
    if settings.app_env == "test" and settings.enable_e2e_routes:
        from app.routers.e2e import router as e2e_router

        app.include_router(e2e_router)

    return app


app = create_app()
