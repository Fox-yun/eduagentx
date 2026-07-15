"""Focused response-contract tests for path version endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers.paths import list_versions


@pytest.mark.asyncio
async def test_list_versions_exposes_stable_version_id():
    version = MagicMock()
    version.id = "version-uuid-2"
    version.path_id = "path-1"
    version.version_number = 2
    version.status = "in_review"
    version.summary = "修订版"
    version.estimated_total_minutes = 180
    version.created_at = "2026-07-13T00:00:00Z"
    version.activated_at = None

    user = MagicMock(id="user-1")
    db = AsyncMock()
    with patch(
        "app.routers.paths.PathService.list_versions",
        new_callable=AsyncMock,
        return_value=[version],
    ):
        result = await list_versions("path-1", user, db)

    assert result["items"][0]["version_id"] == "version-uuid-2"
    assert result["items"][0]["status"] == "draft"

