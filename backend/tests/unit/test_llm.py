"""Unit tests for LLM service with mocked httpx."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm import LLMError, _parse_json, llm_chat, llm_json


class TestParseJson:
    def test_parse_valid_json(self):
        assert _parse_json('{"key": "value"}') == {"key": "value"}

    def test_parse_json_with_code_fences(self):
        text = '```json\n{"key": "value"}\n```'
        assert _parse_json(text) == {"key": "value"}

    def test_parse_json_with_plain_fences(self):
        text = '```\n{"key": "value"}\n```'
        assert _parse_json(text) == {"key": "value"}

    def test_parse_json_strips_whitespace(self):
        assert _parse_json('  {"a": 1}  ') == {"a": 1}

    def test_parse_json_array(self):
        assert _parse_json("[1, 2, 3]") == [1, 2, 3]

    def test_parse_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            _parse_json("not json")


class TestLlmChat:
    @pytest.mark.asyncio
    async def test_missing_api_key_raises(self):
        with patch("app.services.llm.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                llm_api_key="", llm_api_base="https://api.test.com", llm_model="test"
            )
            with pytest.raises(LLMError, match="API key not configured"):
                await llm_chat("system", "user")

    @pytest.mark.asyncio
    async def test_successful_call(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello!"}}],
            "usage": {"total_tokens": 100},
        }
        mock_response.raise_for_status = MagicMock()

        with patch("app.services.llm.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                llm_api_key="test-key",
                llm_api_base="https://api.test.com/v1",
                llm_model="test-model",
            )
            with patch("app.services.llm.httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_cls.return_value = mock_client

                result = await llm_chat("system", "user")
                assert result == "Hello!"

    @pytest.mark.asyncio
    async def test_http_error_raises(self):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.raise_for_status.side_effect = Exception("HTTP 500")

        import httpx

        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=mock_response
        )

        with patch("app.services.llm.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                llm_api_key="test-key",
                llm_api_base="https://api.test.com/v1",
                llm_model="test-model",
            )
            with patch("app.services.llm.httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_cls.return_value = mock_client

                with pytest.raises(LLMError, match="LLM HTTP"):
                    await llm_chat("system", "user")


class TestLlmJson:
    @pytest.mark.asyncio
    async def test_json_mode_returns_parsed(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"result": true}'}}],
            "usage": {},
        }
        mock_response.raise_for_status = MagicMock()

        with patch("app.services.llm.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                llm_api_key="test-key",
                llm_api_base="https://api.test.com/v1",
                llm_model="test-model",
            )
            with patch("app.services.llm.httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_cls.return_value = mock_client

                result = await llm_json("system", "user")
                assert result == {"result": True}
