"""SiliconFlow text-to-speech client used by narrated learning videos."""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx
import structlog

from app.config import get_settings

logger = structlog.get_logger()


@dataclass(frozen=True)
class SpeechResult:
    audio: bytes
    content_type: str
    model: str
    voice: str
    trace_id: str | None


async def synthesize_speech(text: str) -> SpeechResult:
    """Generate one MP3 narration segment through SiliconFlow."""
    settings = get_settings()
    if not settings.llm_api_key:
        raise SpeechError("TTS API key not configured (LLM_API_KEY)")

    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        raise SpeechError("TTS input is empty")

    url = f"{settings.llm_api_base.rstrip('/')}/audio/speech"
    payload = {
        "model": settings.tts_model,
        "voice": settings.tts_voice,
        "input": normalized[:2000],
        "response_format": "mp3",
        "sample_rate": 44100,
        "stream": False,
        "speed": settings.tts_speed,
        "gain": 0,
    }
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=settings.tts_timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error(
            "tts_http_error",
            status=exc.response.status_code,
            body=exc.response.text[:300],
        )
        raise SpeechError(f"TTS HTTP {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        logger.error("tts_request_error", error=str(exc))
        raise SpeechError(f"TTS request failed: {exc}") from exc

    content_type = response.headers.get("content-type", "")
    if not content_type.startswith("audio/") or len(response.content) < 1000:
        raise SpeechError("TTS response did not contain valid audio")

    trace_id = response.headers.get("x-siliconcloud-trace-id")
    logger.info(
        "tts_call_success",
        model=settings.tts_model,
        voice=settings.tts_voice,
        bytes=len(response.content),
        trace_id=trace_id,
    )
    return SpeechResult(
        audio=response.content,
        content_type=content_type,
        model=settings.tts_model,
        voice=settings.tts_voice,
        trace_id=trace_id,
    )


class SpeechError(Exception):
    """Raised when speech synthesis fails or returns invalid audio."""
