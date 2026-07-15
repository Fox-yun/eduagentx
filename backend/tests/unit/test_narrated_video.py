from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import httpx
import imageio_ffmpeg
import pytest
from PIL import Image

from app.services.narrated_video import (
    build_presentation_manifest,
    compose_narrated_video,
    render_slide_image,
)
from app.services.speech import SpeechResult, synthesize_speech

if TYPE_CHECKING:
    from pathlib import Path


COURSE = {
    "introduction": "Python 变量与对象引用。本节通过示例解释变量绑定。",
    "objectives": ["解释变量绑定", "使用 is 验证共享引用"],
    "sections": [
        {"title": "变量名与对象", "content": "变量名不是盒子，而是指向对象的标签。\n对象本身具有类型和值。"},
        {"title": "共享引用", "content": "两个变量名可以指向同一个列表。\n修改列表时两个名称都能观察到变化。"},
        {"title": "重新绑定", "content": "重新赋值只会改变变量名的指向，不会修改原对象。"},
    ],
    "practice_tasks": [{"description": "修改列表并比较 is 和 id 的输出"}],
    "summary": "变量保存对象引用，赋值建立或改变名称与对象之间的绑定关系。",
}


def test_manifest_reuses_course_structure_for_slides_and_narration() -> None:
    manifest = build_presentation_manifest(COURSE)

    assert manifest["resolution"] == "1280x720"
    assert 5 <= len(manifest["slides"]) <= 8
    assert manifest["slides"][0]["kind"] == "title"
    assert any(slide["kind"] == "practice" for slide in manifest["slides"])
    assert all(slide["narration"] for slide in manifest["slides"])


def test_manifest_title_uses_heading_without_introduction_body() -> None:
    content = {
        **COURSE,
        "introduction": (
            "# Python 编程基础和算法的核心概念与术语\n\n"
            "学习 Python 编程基础和算法时，应先建立清晰的术语体系。"
        ),
    }

    manifest = build_presentation_manifest(content)

    assert manifest["title"] == "Python 编程基础和算法的核心概念与术语"
    assert "学习" not in manifest["title"]
    assert len(manifest["title"]) <= 22


def test_manifest_title_ellipsizes_an_overlong_heading() -> None:
    content = {
        **COURSE,
        "introduction": "# 面向零基础学习者的 Python 编程基础、算法设计与工程实践核心概念详解",
    }

    title = build_presentation_manifest(content)["title"]

    assert len(title) == 22
    assert title.endswith("…")


def test_slide_renderer_outputs_16_by_9_png(tmp_path: Path) -> None:
    output = tmp_path / "slide.png"
    render_slide_image(
        {"title": "对象引用", "bullets": ["变量名指向对象", "多个名称可以共享引用"]},
        1,
        3,
        output,
    )

    with Image.open(output) as image:
        assert image.size == (1280, 720)
        assert image.format == "PNG"


def test_compose_video_uses_one_audio_track_and_emits_captions(tmp_path: Path) -> None:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    audio_path = tmp_path / "narration.mp3"
    completed = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=mono",
            "-t",
            "1.5",
            "-q:a",
            "9",
            "-acodec",
            "libmp3lame",
            str(audio_path),
        ],
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0

    speech = SpeechResult(
        audio=audio_path.read_bytes(),
        content_type="audio/mpeg",
        model="FunAudioLLM/CosyVoice2-0.5B",
        voice="FunAudioLLM/CosyVoice2-0.5B:anna",
        trace_id="trace-test",
    )
    manifest = {
        "title": "对象引用",
        "resolution": "1280x720",
        "slides": [
            {"title": "变量名", "bullets": ["名称指向对象"], "narration": "变量名指向对象。"},
            {"title": "共享引用", "bullets": ["两个名称共享列表"], "narration": "两个名称可以共享列表。"},
        ],
    }

    result = compose_narrated_video(manifest, speech)

    assert len(result.video) > 10_000
    assert b"ftyp" in result.video[:64]
    assert result.captions_vtt.startswith("WEBVTT")
    assert "变量名指向对象" in result.captions_vtt
    assert "line:88% position:50% align:center size:72%" in result.captions_vtt
    caption_lines = [
        line
        for line in result.captions_vtt.splitlines()
        if line and "-->" not in line and line != "WEBVTT"
    ]
    assert all(len(line) <= 24 for line in caption_lines)
    assert result.duration_seconds >= 1.4
    assert result.manifest["slides"][1]["end"] == pytest.approx(result.duration_seconds, abs=0.02)


@pytest.mark.asyncio
async def test_siliconflow_speech_client_returns_binary_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient:
        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, **kwargs: object) -> httpx.Response:
            request = httpx.Request("POST", url)
            return httpx.Response(
                200,
                request=request,
                content=b"I" * 2048,
                headers={
                    "content-type": "audio/mpeg",
                    "x-siliconcloud-trace-id": "trace-1",
                },
            )

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: FakeClient())

    # Ensure the test does not depend on a real API key being set in the environment
    from app.config import get_settings

    original = get_settings()
    monkeypatch.setattr(original, "llm_api_key", "test-key-for-unit-test")

    result = await synthesize_speech("欢迎学习 Python。")

    assert result.content_type == "audio/mpeg"
    assert result.trace_id == "trace-1"
    assert len(result.audio) == 2048
