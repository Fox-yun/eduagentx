"""Security tests for the unified learning access guard.

Verifies that require_node_access properly enforces:
  - User can access own path/node
  - Cross-user access denied
  - Archived path access denied
  - Node from wrong version denied
  - Mismatched path/node denied
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_path(id="path-1", user_id="user-1", active_version_id="ver-1", status="active"):
    p = MagicMock()
    p.id = id
    p.user_id = user_id
    p.active_version_id = active_version_id
    p.status = status
    return p


def _make_version(id="ver-1", path_id="path-1", status="active"):
    v = MagicMock()
    v.id = id
    v.path_id = path_id
    v.status = status
    return v


def _make_node(id="node-1", version_id="ver-1"):
    n = MagicMock()
    n.id = id
    n.version_id = version_id
    return n


def _scalar(val):
    r = MagicMock()
    r.scalar_one_or_none.return_value = val
    return r


class TestRequireNodeAccess:
    """Access control enforcement."""

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
        assert ctx.user_id == "user-1"

    @pytest.mark.asyncio
    async def test_other_user_path_denied(self):
        """User A cannot access User B's path (path not found = 404)."""
        from app.core.errors import ApiError
        from app.services.learning_access import require_node_access

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalar(None))  # path not found

        with pytest.raises(ApiError, match="Learning path not found"):
            await require_node_access(db, "user-a", "path-1", "node-1")

    @pytest.mark.asyncio
    async def test_archived_path_denied(self):
        """Archived path raises 403."""
        from app.core.errors import ApiError
        from app.services.learning_access import require_node_access

        db = AsyncMock()
        path = _make_path(status="archived")
        db.execute = AsyncMock(return_value=_scalar(path))

        with pytest.raises(ApiError, match="Learning path is archived"):
            await require_node_access(db, "user-1", "path-1", "node-1")

    @pytest.mark.asyncio
    async def test_no_active_version_denied(self):
        """Path without active version raises 400."""
        from app.core.errors import ApiError
        from app.services.learning_access import require_node_access

        db = AsyncMock()
        path = _make_path(active_version_id=None)
        db.execute = AsyncMock(return_value=_scalar(path))

        with pytest.raises(ApiError, match="Path has no active version"):
            await require_node_access(db, "user-1", "path-1", "node-1")

    @pytest.mark.asyncio
    async def test_node_from_wrong_version_denied(self):
        """Node not in the active version's scope is not found."""
        from app.core.errors import ApiError
        from app.services.learning_access import require_node_access

        db = AsyncMock()

        call_count = 0
        results = [
            _make_path(),
            _make_version(),
            None,  # node not found in this version
        ]

        async def execute(query):
            nonlocal call_count
            idx = min(call_count, len(results) - 1)
            call_count += 1
            return _scalar(results[idx])

        db.execute = AsyncMock(side_effect=execute)

        with pytest.raises(ApiError, match="Learning node not found"):
            await require_node_access(db, "user-1", "path-1", "node-1")

    @pytest.mark.asyncio
    async def test_mismatched_path_and_node(self):
        """Node that exists but belongs to a different path version raises 404."""
        from app.core.errors import ApiError
        from app.services.learning_access import require_node_access

        db = AsyncMock()

        path = _make_path(active_version_id="ver-1")
        version = _make_version(id="ver-1")
        # Node query returns None because the node belongs to "ver-2",
        # not the active "ver-1" — the WHERE clause won't match.
        node = None

        call_count = 0
        results = [path, version, node]

        async def execute(query):
            nonlocal call_count
            idx = min(call_count, len(results) - 1)
            call_count += 1
            return _scalar(results[idx])

        db.execute = AsyncMock(side_effect=execute)

        with pytest.raises(ApiError, match="Learning node not found"):
            await require_node_access(db, "user-1", "path-1", "node-1")
