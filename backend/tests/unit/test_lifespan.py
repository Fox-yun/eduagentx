"""Tests for app/lifespan.py and the workers/tasks.py execute_background_task dispatch."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# lifespan.py
# ---------------------------------------------------------------------------
class TestLifespan:
    @pytest.mark.asyncio
    async def test_development_startup_recovers_stale_tasks(self):
        """Development startup repairs tasks orphaned by a previous process."""
        from app.lifespan import lifespan

        mock_app = MagicMock()
        mock_db = AsyncMock()
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.lifespan.setup_logging"),
            patch("app.lifespan.get_settings") as mock_settings,
            patch("app.lifespan.get_engine"),
            patch("app.lifespan.get_redis"),
            patch("app.lifespan.close_database", new_callable=AsyncMock),
            patch("app.lifespan.close_redis", new_callable=AsyncMock),
            patch("app.core.database.get_session_factory", return_value=mock_factory),
            patch("app.workers.task_runtime.recover_stale_tasks", new_callable=AsyncMock, return_value=["task-1"]) as recover,
            patch("app.workers.inline_runner.run_inline_outbox_poller", new_callable=AsyncMock),
        ):
            mock_settings.return_value = MagicMock(app_env="development")

            async with lifespan(mock_app):
                recover.assert_awaited_once_with(mock_db, finalize_cancel_requests=True)

    @pytest.mark.asyncio
    async def test_lifespan_startup_success(self):
        """All services start successfully."""
        from app.lifespan import lifespan

        mock_app = MagicMock()

        with (
            patch("app.lifespan.setup_logging") as mock_log_setup,
            patch("app.lifespan.get_settings") as mock_settings,
            patch("app.lifespan.get_engine") as mock_engine,
            patch("app.lifespan.get_redis") as mock_redis,
            patch("app.lifespan.close_database", new_callable=AsyncMock) as mock_close_db,
            patch("app.lifespan.close_redis", new_callable=AsyncMock) as mock_close_redis,
        ):
            mock_settings.return_value = MagicMock(app_env="test")

            async with lifespan(mock_app):
                # Inside lifespan — startup complete
                mock_log_setup.assert_called_once()
                mock_engine.assert_called_once()
                mock_redis.assert_called_once()

            # After exit — shutdown cleanup
            mock_close_db.assert_awaited_once()
            mock_close_redis.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_lifespan_db_init_failure_is_graceful(self):
        """Database init failure is caught and logged, not raised."""
        from app.lifespan import lifespan

        mock_app = MagicMock()

        with (
            patch("app.lifespan.setup_logging"),
            patch("app.lifespan.get_settings") as mock_settings,
            patch("app.lifespan.get_engine", side_effect=Exception("DB down")),
            patch("app.lifespan.get_redis"),
            patch("app.lifespan.close_database", new_callable=AsyncMock),
            patch("app.lifespan.close_redis", new_callable=AsyncMock),
        ):
            mock_settings.return_value = MagicMock(app_env="test")

            # Should not raise
            async with lifespan(mock_app):
                pass

    @pytest.mark.asyncio
    async def test_lifespan_redis_init_failure_is_graceful(self):
        """Redis init failure is caught and logged, not raised."""
        from app.lifespan import lifespan

        mock_app = MagicMock()

        with (
            patch("app.lifespan.setup_logging"),
            patch("app.lifespan.get_settings") as mock_settings,
            patch("app.lifespan.get_engine"),
            patch("app.lifespan.get_redis", side_effect=Exception("Redis down")),
            patch("app.lifespan.close_database", new_callable=AsyncMock),
            patch("app.lifespan.close_redis", new_callable=AsyncMock),
        ):
            mock_settings.return_value = MagicMock(app_env="test")

            # Should not raise
            async with lifespan(mock_app):
                pass

    @pytest.mark.asyncio
    async def test_lifespan_shutdown_failure_suppressed(self):
        """Shutdown failures are suppressed, not raised."""
        from app.lifespan import lifespan

        mock_app = MagicMock()

        with (
            patch("app.lifespan.setup_logging"),
            patch("app.lifespan.get_settings") as mock_settings,
            patch("app.lifespan.get_engine"),
            patch("app.lifespan.get_redis"),
            patch("app.lifespan.close_database", new_callable=AsyncMock, side_effect=Exception("close fail")),
            patch("app.lifespan.close_redis", new_callable=AsyncMock, side_effect=Exception("close fail")),
        ):
            mock_settings.return_value = MagicMock(app_env="test")

            # Should not raise even though close fails
            async with lifespan(mock_app):
                pass


# ---------------------------------------------------------------------------
# workers/tasks.py — execute_background_task (lines 38-104)
# ---------------------------------------------------------------------------
class TestExecuteBackgroundTaskDispatch:
    """Test the main Celery dispatch function execute_background_task."""

    def test_dispatch_unknown_task_type(self):
        """Unknown task type should fail with UNKNOWN_TASK_TYPE error."""
        from app.workers.tasks import execute_background_task

        mock_task = MagicMock()
        mock_task.id = "task-1"
        mock_task.task_type = "unknown_type"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_task

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.workers.tasks.get_session_factory", return_value=mock_factory),
            patch("app.workers.tasks.update_task_status", new_callable=AsyncMock),
            patch("app.workers.tasks._cleanup_engine", new_callable=AsyncMock),
        ):
            result = execute_background_task("task-1")

        assert result["status"] == "error"
        assert "Unknown task type" in result["message"]

    def test_dispatch_task_not_found(self):
        """Task not found should return error status."""
        from app.workers.tasks import execute_background_task

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.workers.tasks.get_session_factory", return_value=mock_factory),
            patch("app.workers.tasks.update_task_status", new_callable=AsyncMock),
            patch("app.workers.tasks._cleanup_engine", new_callable=AsyncMock),
        ):
            result = execute_background_task("nonexistent-task")

        assert result["status"] == "error"
        assert "not found" in result["message"].lower()

    def test_dispatch_execution_error(self):
        """When sub-task raises, should return error and mark failed."""
        from app.workers.tasks import execute_background_task

        mock_task = MagicMock()
        mock_task.id = "task-fail"
        mock_task.task_type = "knowledge_index"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_task

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.workers.tasks.get_session_factory", return_value=mock_factory),
            patch("app.workers.tasks.update_task_status", new_callable=AsyncMock),
            patch(
                "app.workers.tasks.get_handler",
                return_value=AsyncMock(side_effect=RuntimeError("boom")),
            ),
            patch("app.workers.tasks._cleanup_engine", new_callable=AsyncMock),
        ):
            result = execute_background_task("task-fail")

        assert result["status"] == "error"
        assert "boom" in result["message"]

    def test_dispatch_success(self):
        """Successful task dispatch returns completed status."""
        from app.workers.tasks import execute_background_task

        mock_task = MagicMock()
        mock_task.id = "task-ok"
        mock_task.task_type = "e2e_progress_test"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_task

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.workers.tasks.get_session_factory", return_value=mock_factory),
            patch("app.workers.tasks.update_task_status", new_callable=AsyncMock),
            patch(
                "app.workers.tasks.get_handler",
                return_value=AsyncMock(return_value={"result": "e2e progress completed"}),
            ),
            patch("app.workers.tasks._cleanup_engine", new_callable=AsyncMock),
        ):
            result = execute_background_task("task-ok")

        assert result["status"] == "completed"
        assert result["result"] == {"result": "e2e progress completed"}
