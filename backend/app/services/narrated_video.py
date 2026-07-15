"""Cost-efficient narrated slide video generation.

One TTS request produces the complete narration.  Slide timings are derived
from narration length, then FFmpeg combines deterministic slide images, audio,
and a WebVTT caption track into a downloadable MP4 learning resource.
"""

from __future__ import annotations

import re
import subprocess  # nosec B404
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

from app.services.presentation_text import extract_presentation_title
from app.services.speech import SpeechResult, synthesize_speech

VIDEO_WIDTH = 1280
VIDEO_HEIGHT = 720
MAX_VIDEO_SLIDES = 8


@dataclass(frozen=True)
class NarratedVideoResult:
    video: bytes
    captions_vtt: str
    manifest: dict[str, Any]
    duration_seconds: float
    tts: SpeechResult


async def generate_narrated_video(unit_content: dict[str, Any]) -> NarratedVideoResult:
    manifest = build_presentation_manifest(unit_content)
    narration = "。".join(slide["narration"] for slide in manifest["slides"])
    tts = await synthesize_speech(narration)
    return compose_narrated_video(manifest, tts)


def build_presentation_manifest(unit_content: dict[str, Any]) -> dict[str, Any]:
    """Build a shared slide/narration manifest from existing course content."""
    introduction = _clean_text(unit_content.get("introduction"))
    title = extract_presentation_title(unit_content)
    objectives = [str(item) for item in _as_list(unit_content.get("objectives"))]
    sections = [item for item in _as_list(unit_content.get("sections")) if isinstance(item, dict)]
    tasks = _as_list(unit_content.get("practice_tasks"))
    summary = _clean_text(unit_content.get("summary"))

    slides: list[dict[str, Any]] = [
        {
            "kind": "title",
            "title": title,
            "bullets": ["个性化学习微课", "讲义、字幕与语音同步生成"],
            "narration": introduction[:420] or f"欢迎学习{title}。本视频将带你建立整体认识。",
        }
    ]
    if objectives:
        slides.append(
            {
                "kind": "objectives",
                "title": "本节学习目标",
                "bullets": objectives[:5],
                "narration": "本节学习目标包括：" + "；".join(objectives[:5]),
            }
        )

    for section in sections[:5]:
        section_title = _clean_text(section.get("title")) or "核心知识点"
        section_content = _clean_text(section.get("content"))
        bullets = _extract_bullets(section.get("content"))
        slides.append(
            {
                "kind": "section",
                "title": section_title[:48],
                "bullets": bullets[:5] or [section_content[:100]],
                "narration": section_content[:650] or f"下面学习{section_title}，请结合课程讲义理解其核心原理。",
            }
        )

    if tasks and len(slides) < MAX_VIDEO_SLIDES:
        task_texts = [_task_text(task) for task in tasks[:4]]
        slides.append(
            {
                "kind": "practice",
                "title": "实践与自检",
                "bullets": task_texts,
                "narration": "完成讲解后，请尝试以下实践：" + "；".join(task_texts),
            }
        )
    if summary and len(slides) < MAX_VIDEO_SLIDES:
        slides.append(
            {
                "kind": "summary",
                "title": "本节小结",
                "bullets": _extract_bullets(summary)[:4] or [summary[:120]],
                "narration": summary[:500],
            }
        )

    return {
        "title": title,
        "aspect_ratio": "16:9",
        "resolution": f"{VIDEO_WIDTH}x{VIDEO_HEIGHT}",
        "slides": slides[:MAX_VIDEO_SLIDES],
    }


def compose_narrated_video(
    manifest: dict[str, Any],
    tts: SpeechResult,
) -> NarratedVideoResult:
    """Render the manifest and narration into MP4 bytes."""
    slides = manifest.get("slides")
    if not isinstance(slides, list) or not slides:
        raise VideoGenerationError("Presentation manifest has no slides")

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    with tempfile.TemporaryDirectory(prefix="eduagentx-video-") as temp_dir:
        root = Path(temp_dir)
        audio_path = root / "narration.mp3"
        audio_path.write_bytes(tts.audio)
        duration = _probe_duration(ffmpeg_exe, audio_path)
        timings = _allocate_timings(slides, duration)

        image_paths: list[Path] = []
        for index, slide in enumerate(slides, start=1):
            image_path = root / f"slide-{index:02d}.png"
            render_slide_image(slide, index, len(slides), image_path)
            image_paths.append(image_path)

        concat_path = root / "slides.txt"
        concat_lines: list[str] = []
        for path, timing in zip(image_paths, timings, strict=True):
            concat_lines.append(f"file '{path.as_posix()}'")
            concat_lines.append(f"duration {timing['duration']:.3f}")
        concat_lines.append(f"file '{image_paths[-1].as_posix()}'")
        concat_path.write_text("\n".join(concat_lines), encoding="utf-8")

        output_path = root / "narrated-course.mp4"
        command = [
            ffmpeg_exe,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-i",
            str(audio_path),
            "-c:v",
            "libx264",
            "-tune",
            "stillimage",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-pix_fmt",
            "yuv420p",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=360, check=False)  # nosec B603
        if completed.returncode != 0 or not output_path.exists():
            raise VideoGenerationError(f"FFmpeg failed: {completed.stderr[-500:]}")

        captions_vtt = _build_vtt(slides, timings)
        enriched_manifest = {
            **manifest,
            "slides": [
                {**slide, "start": timing["start"], "end": timing["end"]}
                for slide, timing in zip(slides, timings, strict=True)
            ],
        }
        return NarratedVideoResult(
            video=output_path.read_bytes(),
            captions_vtt=captions_vtt,
            manifest=enriched_manifest,
            duration_seconds=round(duration, 2),
            tts=tts,
        )


def render_slide_image(
    slide: dict[str, Any],
    index: int,
    total: int,
    output_path: Path,
) -> None:
    image = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), "#F7F8FB")
    draw = ImageDraw.Draw(image)
    title_font = _font(44, bold=True)
    body_font = _font(29)
    small_font = _font(20)

    draw.rounded_rectangle((58, 48, 1222, 660), radius=28, fill="#FFFFFF", outline="#DCE2EC", width=2)
    draw.rounded_rectangle((58, 48, 78, 660), radius=10, fill="#315EFB")
    title = _fit_text(draw, str(slide.get("title", "课程讲解")), title_font, 1050)
    draw.text((108, 92), title, font=title_font, fill="#172033")

    y = 188
    raw_bullets = slide.get("bullets")
    bullets: list[Any] = raw_bullets if isinstance(raw_bullets, list) else []
    for bullet in bullets[:5]:
        lines = _wrap_text(draw, str(bullet), body_font, 970)
        draw.ellipse((112, y + 11, 126, y + 25), fill="#315EFB")
        draw.multiline_text((150, y), "\n".join(lines), font=body_font, fill="#3D475C", spacing=8)
        y += max(62, len(lines) * 42 + 20)
        if y > 555:
            break

    progress_width = round(1050 * index / total)
    draw.rounded_rectangle((108, 612, 1158, 620), radius=4, fill="#E7EBF2")
    draw.rounded_rectangle((108, 612, 108 + progress_width, 620), radius=4, fill="#315EFB")
    draw.text((108, 635), "EduAgentX 个性化学习微课", font=small_font, fill="#7B8497")
    draw.text((1080, 635), f"{index}/{total}", font=small_font, fill="#7B8497")
    image.save(output_path, format="PNG", optimize=True)


def _allocate_timings(slides: list[dict[str, Any]], total_duration: float) -> list[dict[str, float]]:
    weights = [max(len(str(slide.get("narration", ""))), 20) for slide in slides]
    weight_total = sum(weights)
    cursor = 0.0
    timings: list[dict[str, float]] = []
    for index, weight in enumerate(weights):
        duration = total_duration * weight / weight_total
        end = total_duration if index == len(weights) - 1 else cursor + duration
        timings.append({"start": round(cursor, 3), "end": round(end, 3), "duration": round(end - cursor, 3)})
        cursor = end
    return timings


def _probe_duration(ffmpeg_exe: str, audio_path: Path) -> float:
    completed = subprocess.run(  # nosec B603
        [ffmpeg_exe, "-i", str(audio_path), "-f", "null", "-"],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    match = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", completed.stderr)
    if not match:
        raise VideoGenerationError("Unable to determine narration duration")
    hours, minutes, seconds = match.groups()
    duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    if duration <= 0:
        raise VideoGenerationError("Narration duration is invalid")
    return duration


def _build_vtt(slides: list[dict[str, Any]], timings: list[dict[str, float]]) -> str:
    cues = ["WEBVTT", ""]
    for slide, timing in zip(slides, timings, strict=True):
        segments = _caption_segments(str(slide.get("narration", "")))
        weights = [max(len(segment), 1) for segment in segments]
        total_weight = sum(weights)
        cursor = timing["start"]
        for index, (segment, weight) in enumerate(zip(segments, weights, strict=True)):
            end = (
                timing["end"]
                if index == len(segments) - 1
                else cursor + timing["duration"] * weight / total_weight
            )
            cues.extend(
                [
                    (
                        f"{_vtt_time(cursor)} --> {_vtt_time(end)} "
                        "line:88% position:50% align:center size:72%"
                    ),
                    segment,
                    "",
                ]
            )
            cursor = end
    return "\n".join(cues)


def _caption_segments(text: str, max_characters: int = 24) -> list[str]:
    """Split long slide narration into readable one-line caption cues."""
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return [""]
    sentences = [part.strip() for part in re.findall(r"[^。！？!?；;，,]+[。！？!?；;，,]?", cleaned) if part.strip()]
    segments: list[str] = []
    for sentence in sentences:
        while len(sentence) > max_characters:
            segments.append(sentence[:max_characters])
            sentence = sentence[max_characters:]
        if sentence:
            segments.append(sentence)
    return segments or [cleaned[:max_characters]]


def _vtt_time(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc"),
        Path(
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
            if bold
            else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
        ),
        Path(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        ),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    lines: list[str] = []
    current = ""
    for character in text.replace("\n", " "):
        candidate = current + character
        if current and draw.textlength(candidate, font=font) > max_width:
            lines.append(current)
            current = character
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines[:3]


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
) -> str:
    """Ellipsize a single-line label to its actual rendered width."""
    compact = re.sub(r"\s+", " ", text).strip()
    if draw.textlength(compact, font=font) <= max_width:
        return compact
    ellipsis = "…"
    while compact and draw.textlength(f"{compact}{ellipsis}", font=font) > max_width:
        compact = compact[:-1].rstrip()
    return f"{compact}{ellipsis}" if compact else ellipsis


def _extract_bullets(value: Any) -> list[str]:
    text = value if isinstance(value, str) else ""
    bullets: list[str] = []
    for raw_line in text.splitlines():
        line = re.sub(r"^[#>*\-\d.\s]+", "", raw_line).strip()
        line = re.sub(r"[`*_]", "", line)
        if 8 <= len(line) <= 120 and not line.startswith("language-"):
            bullets.append(line)
    if bullets:
        return bullets
    cleaned = _clean_text(text)
    return [part.strip() for part in re.split(r"[。；]", cleaned) if len(part.strip()) >= 8]


def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = re.sub(r"```[\s\S]*?```", "", value)
    text = re.sub(r"[#>*`_\[\]()]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _task_text(task: Any) -> str:
    if isinstance(task, dict):
        return str(task.get("description") or task.get("task") or "完成实践任务")[:120]
    return str(task)[:120]


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


class VideoGenerationError(Exception):
    """Raised when narration or MP4 composition fails."""
