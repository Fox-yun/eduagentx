"""Shared text normalization for generated presentations."""

from __future__ import annotations

import re
from typing import Any

MAX_PRESENTATION_TITLE_LENGTH = 22


def extract_presentation_title(
    unit_content: dict[str, Any],
    *,
    fallback: str = "个性化课程讲解",
    max_length: int = MAX_PRESENTATION_TITLE_LENGTH,
) -> str:
    """Return a concise title without leaking introduction body text.

    Unit introductions commonly start with a Markdown heading followed by a
    paragraph.  Keeping the line boundary is important: flattening the whole
    introduction first can accidentally append that paragraph to the title.
    """
    introduction = unit_content.get("introduction")
    raw_text = introduction if isinstance(introduction, str) else ""
    first_line = next((line.strip() for line in raw_text.splitlines() if line.strip()), "")
    title = re.sub(r"^#{1,6}\s*", "", first_line)
    title = re.sub(r"[`*_\[\]()]", "", title)
    title = re.split(r"[。！？!?]", title, maxsplit=1)[0]
    title = re.sub(r"\s+", " ", title).strip(" -—:：") or fallback

    if max_length < 2 or len(title) <= max_length:
        return title[:max_length] if max_length > 0 else fallback
    return f"{title[: max_length - 1].rstrip()}…"
