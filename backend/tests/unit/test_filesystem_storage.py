from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.services.storage import FileSystemObjectStorage

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
async def test_filesystem_storage_survives_new_instance(tmp_path: Path) -> None:
    key = "resources/user/node/course.pptx"
    first = FileSystemObjectStorage(tmp_path)
    await first.put(key, b"pptx-data")

    restarted = FileSystemObjectStorage(tmp_path)
    assert await restarted.exists(key)
    assert await restarted.get(key) == b"pptx-data"

    await restarted.delete(key)
    assert not await restarted.exists(key)


@pytest.mark.asyncio
async def test_filesystem_storage_rejects_path_traversal(tmp_path: Path) -> None:
    storage = FileSystemObjectStorage(tmp_path)
    with pytest.raises(ValueError, match="escapes storage root"):
        await storage.put("../outside.bin", b"unsafe")
