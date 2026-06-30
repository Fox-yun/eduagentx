"""Tests for app/core/cookies.py, app/core/pagination.py, app/core/request_context.py."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import Column, MetaData, String, Table, select
from starlette.requests import Request

from app.core.errors import ApiError

# Create a real SQLAlchemy table for pagination tests
_metadata = MetaData()
_test_table = Table(
    "_test_items",
    _metadata,
    Column("id", String, primary_key=True),
    Column("created_at", String),
)


# ---------------------------------------------------------------------------
# cookies.py
# ---------------------------------------------------------------------------
class TestCookies:
    def _make_settings(self):
        s = MagicMock()
        s.access_token_ttl_seconds = 900
        s.refresh_token_ttl_seconds = 86400
        s.cookie_secure = False
        s.cookie_samesite = "lax"
        s.cookie_domain = None
        return s

    def test_set_auth_cookies(self):
        from starlette.responses import Response

        from app.core.cookies import set_auth_cookies

        response = Response()
        settings = self._make_settings()

        with patch("app.core.cookies.get_settings", return_value=settings):
            set_auth_cookies(response, "acc_tok", "ref_tok", "csrf_tok")

        # Verify cookies were set via the response headers
        cookie_header = response.raw_headers
        cookie_keys = [h[1].decode().split("=")[0] for h in cookie_header if h[0] == b"set-cookie"]
        assert "access_token" in cookie_keys
        assert "refresh_token" in cookie_keys
        assert "csrftoken" in cookie_keys

    def test_clear_auth_cookies(self):
        from starlette.responses import Response

        from app.core.cookies import clear_auth_cookies

        response = Response()
        settings = self._make_settings()

        with patch("app.core.cookies.get_settings", return_value=settings):
            clear_auth_cookies(response)

        # delete_cookie sets the cookie to empty with max-age=0
        cookie_header = response.raw_headers
        cookie_keys = [h[1].decode().split("=")[0] for h in cookie_header if h[0] == b"set-cookie"]
        assert "access_token" in cookie_keys
        assert "refresh_token" in cookie_keys
        assert "csrftoken" in cookie_keys

    def test_create_auth_response(self):
        from app.core.cookies import create_auth_response

        settings = self._make_settings()

        with patch("app.core.cookies.get_settings", return_value=settings):
            response = create_auth_response("acc", "ref", "csrf", body={"ok": True})

        assert response.status_code == 200
        body = json.loads(response.body)
        assert body == {"ok": True}

    def test_create_auth_response_no_body(self):
        from app.core.cookies import create_auth_response

        settings = self._make_settings()

        with patch("app.core.cookies.get_settings", return_value=settings):
            response = create_auth_response("acc", "ref", "csrf")

        body = json.loads(response.body)
        assert body == {}


# ---------------------------------------------------------------------------
# pagination.py
# ---------------------------------------------------------------------------
class TestPagination:
    def test_encode_decode_roundtrip(self):
        from app.core.pagination import decode_cursor, encode_cursor

        data = {"order": "2024-01-01T00:00:00", "id": "abc-123"}
        encoded = encode_cursor(data)
        decoded = decode_cursor(encoded)
        assert decoded["order"] == data["order"]
        assert decoded["id"] == data["id"]

    def test_decode_invalid_cursor_raises(self):
        from app.core.pagination import decode_cursor

        with pytest.raises(ApiError) as exc:
            decode_cursor("not-valid-base64!!!")
        assert exc.value.code == "INVALID_CURSOR"

    @pytest.mark.asyncio
    async def test_paginate_query_basic(self):
        from app.core.pagination import paginate_query

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()

        # Use a real SQLAlchemy query
        base_query = select(_test_table)

        # Mock the count query result
        count_result = MagicMock()
        count_result.scalar.return_value = 5

        # Mock the data query — 3 rows (less than limit, so no next page)
        row1 = MagicMock()
        row1.created_at = "2024-01-03"
        row1.id = "id-3"
        row2 = MagicMock()
        row2.created_at = "2024-01-02"
        row2.id = "id-2"
        row3 = MagicMock()
        row3.created_at = "2024-01-01"
        row3.id = "id-1"

        data_result = MagicMock()
        data_result.scalars.return_value.all.return_value = [row1, row2, row3]

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return count_result
            return data_result

        mock_db.execute = mock_execute

        result = await paginate_query(
            db=mock_db,
            query=base_query,
            cursor=None,
            limit=10,
            order_column=_test_table.c.created_at,
            id_column=_test_table.c.id,
            model_class=MagicMock(),
        )

        assert result["total"] == 5
        assert len(result["items"]) == 3
        assert result["next_cursor"] is None

    @pytest.mark.asyncio
    async def test_paginate_query_with_next_page(self):
        from app.core.pagination import paginate_query

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        count_result = MagicMock()
        count_result.scalar.return_value = 10

        # Return limit+1 items to trigger has_next
        rows = []
        for i in range(4):
            row = MagicMock()
            row.created_at = f"2024-01-{4 - i:02d}"
            row.id = f"id-{4 - i}"
            rows.append(row)

        data_result = MagicMock()
        data_result.scalars.return_value.all.return_value = rows

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return count_result
            return data_result

        mock_db.execute = mock_execute

        base_query = select(_test_table)

        result = await paginate_query(
            db=mock_db,
            query=base_query,
            cursor=None,
            limit=3,
            order_column=_test_table.c.created_at,
            id_column=_test_table.c.id,
            model_class=MagicMock(),
        )

        assert result["total"] == 10
        assert len(result["items"]) == 3
        assert result["next_cursor"] is not None

    @pytest.mark.asyncio
    async def test_paginate_query_invalid_limit_clamped(self):
        from app.core.pagination import paginate_query

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        count_result = MagicMock()
        count_result.scalar.return_value = 0

        async def mock_execute(query):
            return count_result

        mock_db.execute = mock_execute

        base_query = select(_test_table)

        result = await paginate_query(
            db=mock_db,
            query=base_query,
            cursor=None,
            limit=999,  # > 100, clamped to 20
            order_column=_test_table.c.created_at,
            id_column=_test_table.c.id,
            model_class=MagicMock(),
        )

        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_paginate_query_with_cursor(self):
        from app.core.pagination import encode_cursor, paginate_query

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        mock_db.add = MagicMock()
        mock_db.add_all = MagicMock()
        count_result = MagicMock()
        count_result.scalar.return_value = 2

        data_result = MagicMock()
        data_result.scalars.return_value.all.return_value = []

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return count_result
            return data_result

        mock_db.execute = mock_execute

        cursor = encode_cursor({"order": "2024-01-02", "id": "id-2"})

        result = await paginate_query(
            db=mock_db,
            query=select(_test_table),
            cursor=cursor,
            limit=10,
            order_column=_test_table.c.created_at,
            id_column=_test_table.c.id,
            model_class=MagicMock(),
        )

        assert result["total"] == 2


# ---------------------------------------------------------------------------
# request_context.py
# ---------------------------------------------------------------------------
class TestRequestContext:
    def test_get_client_ip_forwarded_for(self):
        from app.core.request_context import get_client_ip

        request = MagicMock(spec=Request)
        request.headers = {"x-forwarded-for": "1.2.3.4, 5.6.7.8"}
        request.client = None

        assert get_client_ip(request) == "1.2.3.4"

    def test_get_client_ip_real_ip(self):
        from app.core.request_context import get_client_ip

        request = MagicMock(spec=Request)
        request.headers = {"x-real-ip": "10.0.0.1"}
        request.client = None

        assert get_client_ip(request) == "10.0.0.1"

    def test_get_client_ip_direct(self):
        from app.core.request_context import get_client_ip

        request = MagicMock(spec=Request)
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.1"

        assert get_client_ip(request) == "192.168.1.1"

    def test_get_client_ip_no_client(self):
        from app.core.request_context import get_client_ip

        request = MagicMock(spec=Request)
        request.headers = {}
        request.client = None

        assert get_client_ip(request) is None
