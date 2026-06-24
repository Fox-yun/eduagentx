"""Tests for unified error handling."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from app.core.errors import ApiError, register_error_handlers


@pytest.fixture
def app():
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/test-validation-error")
    async def validation_error():
        raise RequestValidationError(errors=[{"loc": ("body",), "msg": "field required", "type": "value_error"}])

    @app.get("/test-api-error")
    async def api_error():
        raise ApiError(code="TEST_ERROR", message="Test error message", status_code=400)

    @app.get("/test-unhandled-error")
    async def unhandled_error():
        raise RuntimeError("Unexpected error")

    return app


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


def test_validation_error_returns_nested_structure(client):
    response = client.get("/test-validation-error")
    assert response.status_code == 422
    body = response.json()
    assert "error" in body
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["message"] == "Request validation failed"
    assert body["error"]["details"] is not None


def test_api_error_returns_nested_structure(client):
    response = client.get("/test-api-error")
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "TEST_ERROR"
    assert body["error"]["message"] == "Test error message"


def test_unhandled_error_returns_500(client):
    response = client.get("/test-unhandled-error")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["message"] == "An internal error occurred"
