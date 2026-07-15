"""Tests for health check endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_health_live(client):
    response = await client.get("/health/live")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == "4.1.0"


async def test_health_live_has_request_id(client):
    response = await client.get("/health/live")
    assert "X-Request-ID" in response.headers


async def test_health_ready_success(client):
    with (
        patch("app.main.check_database_connection", new_callable=AsyncMock, return_value=True),
        patch("app.main.check_redis_connection", new_callable=AsyncMock, return_value=True),
    ):
        response = await client.get("/health/ready")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ready"
        assert body["database"] is True
        assert body["redis"] is True


async def test_health_ready_db_failure(client):
    with (
        patch("app.main.check_database_connection", new_callable=AsyncMock, return_value=False),
        patch("app.main.check_redis_connection", new_callable=AsyncMock, return_value=True),
    ):
        response = await client.get("/health/ready")
        assert response.status_code == 503


async def test_health_ready_redis_failure(client):
    with (
        patch("app.main.check_database_connection", new_callable=AsyncMock, return_value=True),
        patch("app.main.check_redis_connection", new_callable=AsyncMock, return_value=False),
    ):
        response = await client.get("/health/ready")
        assert response.status_code == 503
