"""Tests for Request ID middleware."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.request_context import RequestIDMiddleware


@pytest.fixture
def app():
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return {"ok": True}

    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_generates_request_id_when_missing(client):
    response = client.get("/test")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    assert response.headers["X-Request-ID"].startswith("req_")


def test_preserves_client_request_id(client):
    response = client.get("/test", headers={"X-Request-ID": "req_custom_123"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req_custom_123"


def test_generates_new_id_for_empty_header(client):
    response = client.get("/test", headers={"X-Request-ID": ""})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"].startswith("req_")
    assert response.headers["X-Request-ID"] != ""
