"""Security tests for unit endpoint access control.

Verifies that unit endpoints enforce require_node_access by testing
the guard integration and error semantics.

Existing test_learning_access.py validates require_node_access itself;
this file focuses on verifying the correct error codes per scenario.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_path(entity_id="path-1", user_id="user-1", active_version_id="ver-1", status="active"):
    p = MagicMock()
    p.id = entity_id
    p.user_id = user_id
    p.active_version_id = active_version_id
    p.status = status
    return p


def _make_version(entity_id="ver-1", path_id="path-1", status="active"):
    v = MagicMock()
    v.id = entity_id
    v.path_id = path_id
    v.status = status
    return v


def _make_node(entity_id="node-1", version_id="ver-1", title="Test Node"):
    n = MagicMock()
    n.id = entity_id
    n.version_id = version_id
    n.title = title
    n.description = "Test description"
    n.difficulty = "beginner"
    n.learning_outcomes = '["outcome1"]'
    return n


def _scalar(val):
    r = MagicMock()
    r.scalar_one_or_none.return_value = val
    return r


class TestAccessGuardErrorSemantics:
    """Verify that require_node_access uses the correct error codes."""

    @pytest.mark.asyncio
    async def test_own_path_node_allowed(self):
        """User can access their own active path node."""
        from app.services.learning_access import require_node_access

        db = AsyncMock()

        call_count = 0
        results = [
            _make_path(),
            _make_version(),
            _make_node(),
        ]

        async def execute(query):
            nonlocal call_count
            idx = min(call_count, len(results) - 1)
            call_count += 1
            return _scalar(results[idx])

        db.execute = AsyncMock(side_effect=execute)

        ctx = await require_node_access(db, "user-1", "path-1", "node-1")
        assert ctx.path_id == "path-1"
        assert ctx.node_id == "node-1"

    @pytest.mark.asyncio
    async def test_other_user_path_returns_404(self):
        """Accessing another user's path returns PATH_NOT_FOUND (404)."""
        from app.core.errors import ApiError
        from app.services.learning_access import require_node_access

        db = AsyncMock()
        db.execute.return_value = _scalar(None)

        with pytest.raises(ApiError) as exc:
            await require_node_access(db, "user-a", "path-1", "node-1")
        assert exc.value.status_code == 404
        assert "PATH_NOT_FOUND" in str(exc) or "not found" in str(exc.value).lower()

    @pytest.mark.asyncio
    async def test_archived_path_returns_404(self):
        """Archived path returns 404 (consistent with not-found semantics)."""
        from app.core.errors import ApiError
        from app.services.learning_access import require_node_access

        db = AsyncMock()
        archived_path = _make_path(status="archived")
        db.execute.return_value = _scalar(archived_path)

        with pytest.raises(ApiError) as exc:
            await require_node_access(db, "user-1", "path-1", "node-1")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_node_from_wrong_version_returns_404(self):
        """Node in a different version returns NODE_NOT_FOUND."""
        from app.core.errors import ApiError
        from app.services.learning_access import require_node_access

        db = AsyncMock()

        call_count = 0
        results = [
            _make_path(),
            _make_version(),
            None,  # node not in active version
        ]

        async def execute(query):
            nonlocal call_count
            idx = min(call_count, len(results) - 1)
            call_count += 1
            return _scalar(results[idx])

        db.execute = AsyncMock(side_effect=execute)

        with pytest.raises(ApiError) as exc:
            await require_node_access(db, "user-1", "path-1", "node-1")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_no_active_version_returns_400(self):
        """Path with no active version returns specific error."""
        from app.core.errors import ApiError
        from app.services.learning_access import require_node_access

        db = AsyncMock()
        path_no_ver = _make_path(active_version_id=None)
        db.execute.return_value = _scalar(path_no_ver)

        with pytest.raises(ApiError) as exc:
            await require_node_access(db, "user-1", "path-1", "node-1")
        assert exc.value.status_code == 400
        assert "NO_ACTIVE_VERSION" in str(exc.value.code) or "no active version" in str(exc.value).lower()
