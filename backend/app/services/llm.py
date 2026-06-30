"""LLM service — OpenAI-compatible chat completion via httpx.

Falls back to template-based generation if the API is unavailable.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import structlog

from app.config import get_settings

logger = structlog.get_logger()

_LLM_TIMEOUT = 120.0  # seconds


async def llm_chat(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    response_format: dict[str, str] | None = None,
) -> str:
    """Call an OpenAI-compatible chat completion endpoint.

    Returns the assistant message content as a string.
    Raises ``LLMError`` on HTTP or parsing failures.
    """
    settings = get_settings()

    if not settings.llm_api_key:
        raise LLMError("LLM API key not configured (LLM_API_KEY)")

    url = f"{settings.llm_api_base.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }
    body: dict[str, Any] = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format:
        body["response_format"] = response_format

    try:
        async with httpx.AsyncClient(timeout=_LLM_TIMEOUT) as client:
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            content: str = data["choices"][0]["message"]["content"]
            logger.info("llm_call_success", model=settings.llm_model, tokens=data.get("usage"))
            return content
    except httpx.HTTPStatusError as exc:
        logger.error("llm_http_error", status=exc.response.status_code, body=exc.response.text[:500])
        raise LLMError(f"LLM HTTP {exc.response.status_code}") from exc
    except (httpx.RequestError, KeyError, IndexError) as exc:
        logger.error("llm_call_error", error=str(exc))
        raise LLMError(f"LLM call failed: {exc}") from exc


async def llm_json(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> Any:
    """Call LLM and parse the response as JSON.

    Tries ``response_format={"type": "json_object"}`` first.
    Falls back to extracting JSON from markdown code fences.
    """
    try:
        raw = await llm_chat(
            system_prompt,
            user_message,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
    except LLMError:
        # Retry without response_format (some providers don't support it)
        raw = await llm_chat(
            system_prompt,
            user_message,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    return _parse_json(raw)


def _parse_json(text: str) -> Any:
    """Extract JSON from LLM output, handling code fences."""
    text = text.strip()
    # Strip markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last fence lines
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return json.loads(text)


class LLMError(Exception):
    """Raised when an LLM API call fails."""
