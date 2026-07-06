"""Unit tests for ResourceService.download_resource_binary.

Verifies:
  - Binary download works for PPTX resources (ready status)
  - Binary download works for code_zip resources (ready status)
  - Correct filename and content-type are returned
  - Non-binary resource types are rejected (400)
  - Non-existent resources return 404
  - Not-ready resources return 409
  - Missing storage key returns 404

Run with:
    pytest tests/unit/test_resource_download.py -v
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.errors import ApiError
from app.models.unit import LearningResource
from app.services.resources import ResourceService


def _make_resource(**overrides) -> LearningResource:
    defaults = {
        "id": str(uuid.uuid4()),
        "user_id": "user-1",
        "path_id": "path-1",
        "node_id": "node-1",
        "resource_type": "pptx",
        "status": "ready",
        "active_task_id": None,
        "content": {"slide_count": 5},
        "error_code": None,
        "error_message": None,
        "storage_key": "resources/user-1/node-1/presentation.pptx",
        "storage_provider": "minio",
    }
    defaults.update(overrides)
    res = MagicMock(spec=LearningResource)
    for k, v in defaults.items():
        setattr(res, k, v)
    return res


def _mock_scalar_result(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


class TestDownloadResourceBinary:
    """Tests for ResourceService.download_resource_binary."""

    @pytest.fixture
    def service(self):
        db = MagicMock()
        svc = ResourceService(db)
        svc.storage = AsyncMock()
        return svc

    async def test_download_pptx_success(self, service):
        """PPTX download returns bytes, filename, and correct content-type."""
        fake_bytes = b"fake-pptx-content"
        service.storage.get = AsyncMock(return_value=fake_bytes)
        resource = _make_resource(resource_type="pptx", storage_key="resources/u1/n1/presentation.pptx")
        service.db.execute = AsyncMock(return_value=_mock_scalar_result(resource))

        file_bytes, filename, content_type = await service.download_resource_binary(
            "path-1", "node-1", "user-1", "pptx"
        )

        assert file_bytes == fake_bytes
        assert filename == "node-1-presentation.pptx"
        assert content_type == "application/vnd.openxmlformats-officedocument.presentationml.presentation"

    async def test_download_code_zip_success(self, service):
        """Code ZIP download returns bytes, filename, and correct content-type."""
        fake_bytes = b"fake-zip-content"
        service.storage.get = AsyncMock(return_value=fake_bytes)
        resource = _make_resource(resource_type="code_zip", storage_key="resources/u1/n1/code-project.zip")
        service.db.execute = AsyncMock(return_value=_mock_scalar_result(resource))

        file_bytes, filename, content_type = await service.download_resource_binary(
            "path-1", "node-1", "user-1", "code_zip"
        )

        assert file_bytes == fake_bytes
        assert filename == "node-1-code-project.zip"
        assert content_type == "application/zip"

    async def test_download_non_binary_type_rejected(self, service):
        """Non-binary resource types raise RESOURCE_NOT_BINARY (400)."""
        with pytest.raises(ApiError) as exc_info:
            await service.download_resource_binary("path-1", "node-1", "user-1", "interactive_cards")
        assert exc_info.value.status_code == 400
        assert exc_info.value.code == "RESOURCE_NOT_BINARY"

    async def test_download_nonexistent_resource_404(self, service):
        """Non-existent resource raises RESOURCE_NOT_FOUND (404)."""
        service.db.execute = AsyncMock(return_value=_mock_scalar_result(None))

        with pytest.raises(ApiError) as exc_info:
            await service.download_resource_binary("path-1", "node-1", "user-1", "pptx")
        assert exc_info.value.status_code == 404
        assert exc_info.value.code == "RESOURCE_NOT_FOUND"

    async def test_download_not_ready_resource_409(self, service):
        """Not-ready resource raises RESOURCE_NOT_READY (409)."""
        resource = _make_resource(status="generating")
        service.db.execute = AsyncMock(return_value=_mock_scalar_result(resource))

        with pytest.raises(ApiError) as exc_info:
            await service.download_resource_binary("path-1", "node-1", "user-1", "pptx")
        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "RESOURCE_NOT_READY"

    async def test_download_missing_storage_key_404(self, service):
        """Resource with no storage_key raises RESOURCE_ARTIFACT_NOT_FOUND (404)."""
        resource = _make_resource(storage_key=None)
        service.db.execute = AsyncMock(return_value=_mock_scalar_result(resource))

        with pytest.raises(ApiError) as exc_info:
            await service.download_resource_binary("path-1", "node-1", "user-1", "pptx")
        assert exc_info.value.status_code == 404
        assert exc_info.value.code == "RESOURCE_ARTIFACT_NOT_FOUND"

    async def test_download_storage_failure_404(self, service):
        """When storage.get() raises, returns RESOURCE_ARTIFACT_NOT_FOUND (404)."""
        resource = _make_resource()
        service.db.execute = AsyncMock(return_value=_mock_scalar_result(resource))
        service.storage.get = AsyncMock(side_effect=KeyError("not found"))

        with pytest.raises(ApiError) as exc_info:
            await service.download_resource_binary("path-1", "node-1", "user-1", "pptx")
        assert exc_info.value.status_code == 404
        assert exc_info.value.code == "RESOURCE_ARTIFACT_NOT_FOUND"
