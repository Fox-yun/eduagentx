"""Deterministic text chunking for the knowledge base.

Splits parsed document sections into chunks of 800-1200 tokens with
10-15% overlap. Uses a simple word-based token approximation
(~0.75 words per token for mixed CJK/English content).

The chunker is deterministic: given the same input text, it always
produces the same chunks. This enables version-based reindexing —
if the content hasn't changed, the chunks are identical.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from app.services.document_parser import ParsedSection


@dataclass
class Chunk:
    """A chunk of content ready for storage."""

    content: str
    chunk_index: int
    token_count: int
    page_number: int | None = None
    section_title: str | None = None
    content_hash: str = ""


# Chunking parameters
TARGET_MIN_TOKENS = 800
TARGET_MAX_TOKENS = 1200
OVERLAP_RATIO = 0.12  # 12% overlap


def estimate_token_count(text: str) -> int:
    """Estimate token count for text.

    Uses a heuristic: ~0.75 words per token for English,
    ~1 token per CJK character. This is approximate but
    deterministic and doesn't require a tokenizer dependency.
    """
    # Count CJK characters (common ranges)
    cjk_count = 0
    other_chars = 0

    for ch in text:
        code = ord(ch)
        # CJK Unified Ideographs, Hiragana, Katakana, Hangul
        if (
            0x4E00 <= code <= 0x9FFF  # CJK Unified Ideographs
            or 0x3040 <= code <= 0x30FF  # Hiragana + Katakana
            or 0xAC00 <= code <= 0xD7AF  # Hangul
            or 0x3400 <= code <= 0x4DBF  # CJK Extension A
        ):
            cjk_count += 1
        elif ch.isalpha():
            other_chars += 1

    # Rough approximation
    # CJK: ~1 token per char
    # Latin: ~0.75 tokens per word (word ≈ 1.3 chars on average)
    cjk_tokens = cjk_count
    latin_tokens = int(other_chars / 1.3 * 0.75)

    return cjk_tokens + latin_tokens


def chunk_sections(sections: list[ParsedSection]) -> list[Chunk]:
    """Chunk parsed sections into storage-ready chunks.

    Args:
        sections: List of ParsedSection from the document parser

    Returns:
        List of Chunk objects with deterministic chunk_index starting at 0
    """
    chunks: list[Chunk] = []
    chunk_index = 0

    # Flatten all sections into a text stream with metadata markers
    # Each chunk may span multiple sections, but we track the primary
    # section's page_number and title for the first section in the chunk.
    all_words: list[tuple[str, int | None, str | None]] = []  # (word, page, title)

    for section in sections:
        words = section.text.split()
        for word in words:
            all_words.append((word, section.page_number, section.section_title))

    if not all_words:
        return chunks

    # Calculate overlap in words
    overlap_words = int(TARGET_MAX_TOKENS * OVERLAP_RATIO)

    # Slide through the word list
    pos = 0
    while pos < len(all_words):
        # Take up to TARGET_MAX_TOKENS words
        end = min(pos + TARGET_MAX_TOKENS, len(all_words))
        window = all_words[pos:end]

        # Build chunk text
        chunk_text = " ".join(w[0] for w in window)
        token_count = estimate_token_count(chunk_text)

        # If token count is too low and we're at the end, merge with previous
        if token_count < TARGET_MIN_TOKENS and len(chunks) > 0 and end == len(all_words):
            # Merge into last chunk
            last = chunks[-1]
            last.content = last.content + " " + chunk_text
            last.token_count = estimate_token_count(last.content)
            last.content_hash = _hash_content(last.content)
            break

        chunk = Chunk(
            content=chunk_text,
            chunk_index=chunk_index,
            token_count=token_count,
            page_number=window[0][1],
            section_title=window[0][2],
            content_hash=_hash_content(chunk_text),
        )
        chunks.append(chunk)
        chunk_index += 1

        # Move forward, with overlap
        advance = end - pos - overlap_words
        if advance <= 0:
            advance = end - pos  # No overlap if chunk is small
        pos += advance

    return chunks


def _hash_content(text: str) -> str:
    """Compute SHA-256 hash of content for deduplication."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunks_to_dicts(chunks: list[Chunk]) -> list[dict[str, Any]]:
    """Convert Chunk objects to dicts for storage."""
    return [
        {
            "content": c.content,
            "chunk_index": c.chunk_index,
            "token_count": c.token_count,
            "page_number": c.page_number,
            "section_title": c.section_title,
            "content_hash": c.content_hash,
        }
        for c in chunks
    ]
