"""Object storage abstraction layer.

Provides a Protocol-based interface so business code never depends
directly on MinIO or any specific storage SDK.

Three implementations:
  - InMemoryObjectStorage: for unit tests and local dev without MinIO
  - FileSystemObjectStorage: persistent local development storage
  - MinioObjectStorage: production-grade S3-compatible storage

The factory `get_object_storage()` reads settings to decide which to use.
"""

from __future__ import annotations

import asyncio
import io
import os
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import structlog

from app.config import get_settings

logger = structlog.get_logger()


@runtime_checkable
class ObjectStorage(Protocol):
    """Abstract object storage interface."""

    async def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        """Upload an object."""
        ...

    async def get(self, key: str) -> bytes:
        """Download an object. Raises KeyError if not found."""
        ...

    async def delete(self, key: str) -> None:
        """Delete an object. Idempotent — no error if not found."""
        ...

    async def exists(self, key: str) -> bool:
        """Check if an object exists."""
        ...


class InMemoryObjectStorage:
    """In-memory object storage for tests and local dev.

    Thread-safe via asyncio.Lock. Contents are lost on restart.
    """

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}
        self._lock = asyncio.Lock()

    async def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        async with self._lock:
            self._store[key] = data

    async def get(self, key: str) -> bytes:
        async with self._lock:
            if key not in self._store:
                raise KeyError(f"Object not found: {key}")
            return self._store[key]

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._store.pop(key, None)

    async def exists(self, key: str) -> bool:
        async with self._lock:
            return key in self._store


class FileSystemObjectStorage:
    """Persistent local object storage with traversal-safe keys."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).expanduser().resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, key: str) -> Path:
        normalized = key.replace("\\", "/").lstrip("/")
        if not normalized:
            raise ValueError("Object key cannot be empty")
        path = (self._root / normalized).resolve()
        if path != self._root and self._root not in path.parents:
            raise ValueError(f"Object key escapes storage root: {key}")
        return path

    async def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        path = self._path_for(key)

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
            temporary.write_bytes(data)
            temporary.replace(path)

        await asyncio.to_thread(_write)

    async def get(self, key: str) -> bytes:
        path = self._path_for(key)
        try:
            return await asyncio.to_thread(path.read_bytes)
        except FileNotFoundError as exc:
            raise KeyError(f"Object not found: {key}") from exc

    async def delete(self, key: str) -> None:
        path = self._path_for(key)

        def _delete() -> None:
            try:
                path.unlink()
            except FileNotFoundError:
                return

        await asyncio.to_thread(_delete)

    async def exists(self, key: str) -> bool:
        return await asyncio.to_thread(self._path_for(key).is_file)


class MinioObjectStorage:
    """MinIO / S3-compatible object storage.

    Uses minio async SDK. Requires MINIO_ENDPOINT, MINIO_ACCESS_KEY,
    MINIO_SECRET_KEY, and MINIO_BUCKET settings.
    """

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool = False,
    ) -> None:
        self._endpoint = endpoint
        self._access_key = access_key
        self._secret_key = secret_key
        self._bucket = bucket
        self._secure = secure
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazily create the MinIO client."""
        if self._client is not None:
            return self._client

        from minio import Minio

        self._client = Minio(
            self._endpoint,
            access_key=self._access_key,
            secret_key=self._secret_key,
            secure=self._secure,
        )

        # Ensure bucket exists
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)
            logger.info("minio_bucket_created", bucket=self._bucket)

        return self._client

    async def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        client = self._get_client()
        stream = io.BytesIO(data)
        await asyncio.to_thread(
            client.put_object,
            self._bucket,
            key,
            stream,
            length=len(data),
            content_type=content_type,
        )

    async def get(self, key: str) -> bytes:
        client = self._get_client()
        try:
            response = await asyncio.to_thread(client.get_object, self._bucket, key)
            try:
                data: bytes = response.read()
                return data
            finally:
                response.close()
                response.release_conn()
        except Exception as e:
            raise KeyError(f"Object not found: {key}") from e

    async def delete(self, key: str) -> None:
        client = self._get_client()
        await asyncio.to_thread(client.remove_object, self._bucket, key)

    async def exists(self, key: str) -> bool:
        client = self._get_client()
        try:
            await asyncio.to_thread(client.stat_object, self._bucket, key)
            return True
        except Exception:
            return False


# Singleton instances keyed by settings
_inmemory_instance: InMemoryObjectStorage | None = None
_filesystem_instance: FileSystemObjectStorage | None = None
_minio_instance: MinioObjectStorage | None = None


def get_object_storage() -> ObjectStorage:
    """Factory: return the configured object storage instance.

    Tests use isolated in-memory storage. Other environments use persistent
    filesystem storage by default and MinIO when configured.
    """
    global _inmemory_instance, _filesystem_instance, _minio_instance

    settings = get_settings()

    # Keep tests isolated, but persist local development artifacts across API
    # restarts so database metadata never points at vanished in-memory bytes.
    if not settings.minio_endpoint:
        if settings.is_testing:
            if _inmemory_instance is None:
                _inmemory_instance = InMemoryObjectStorage()
            return _inmemory_instance
        if _filesystem_instance is None:
            _filesystem_instance = FileSystemObjectStorage(settings.local_storage_path)
        return _filesystem_instance

    # Use MinIO
    if _minio_instance is None:
        _minio_instance = MinioObjectStorage(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            bucket=settings.minio_bucket,
            secure=settings.minio_secure,
        )
    return _minio_instance


def reset_storage_for_tests() -> None:
    """Reset storage singletons — call in test fixtures."""
    global _inmemory_instance, _filesystem_instance, _minio_instance
    _inmemory_instance = None
    _filesystem_instance = None
    _minio_instance = None
