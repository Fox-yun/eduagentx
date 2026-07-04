"""Document parsing for the knowledge base.

Supports: PDF, TXT, Markdown, DOCX, CSV, JSON.

Each parser returns a list of `ParsedSection` objects — each containing
extracted text and optional metadata (page_number, section_title).
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class ParsedSection:
    """A section of parsed content from a document."""

    text: str
    page_number: int | None = None
    section_title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def parse_document(content: bytes, mime_type: str, filename: str = "") -> list[ParsedSection]:
    """Parse a document and return its content as sections.

    Args:
        content: Raw file bytes
        mime_type: MIME type of the file
        filename: Original filename (for extension fallback)

    Returns:
        List of ParsedSection objects

    Raises:
        ValueError: If the MIME type is unsupported or parsing fails
    """
    parser_fn = _get_parser(mime_type, filename)
    if parser_fn is None:
        raise ValueError(f"Unsupported MIME type: {mime_type}")

    try:
        result: list[ParsedSection] = parser_fn(content)
        return result
    except Exception as e:
        logger.error("document_parse_failed", filename=filename, mime_type=mime_type, error=str(e))
        raise ValueError(f"Failed to parse {filename}: {e}") from e


def _get_parser(mime_type: str, filename: str) -> Any | None:
    """Get the appropriate parser function for the MIME type."""
    # Normalize
    mime_type = mime_type.lower().strip()

    if mime_type == "application/pdf":
        return _parse_pdf
    if mime_type in ("text/plain", "text/txt"):
        return _parse_txt
    if mime_type in ("text/markdown", "text/x-markdown"):
        return _parse_markdown
    if mime_type in ("application/vnd.openxmlformats-officedocument.wordprocessingml.document",):
        return _parse_docx
    if mime_type == "text/csv":
        return _parse_csv
    if mime_type == "application/json":
        return _parse_json

    # Fallback by extension
    if filename:
        ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
        ext_map = {
            "pdf": _parse_pdf,
            "txt": _parse_txt,
            "md": _parse_markdown,
            "markdown": _parse_markdown,
            "docx": _parse_docx,
            "csv": _parse_csv,
            "json": _parse_json,
        }
        return ext_map.get(ext)

    return None


# ---------------------------------------------------------------------------
# Individual parsers
# ---------------------------------------------------------------------------


def _parse_pdf(content: bytes) -> list[ParsedSection]:
    """Parse PDF using pypdf."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    sections: list[ParsedSection] = []

    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        text = text.strip()
        if text:
            sections.append(
                ParsedSection(
                    text=text,
                    page_number=i + 1,
                )
            )

    if not sections:
        raise ValueError("PDF contains no extractable text (may be image-only)")

    return sections


def _parse_txt(content: bytes) -> list[ParsedSection]:
    """Parse plain text."""
    text = content.decode("utf-8", errors="replace")
    text = text.strip()
    if not text:
        raise ValueError("Text file is empty")
    return [ParsedSection(text=text)]


def _parse_markdown(content: bytes) -> list[ParsedSection]:
    """Parse Markdown, splitting on headings."""
    text = content.decode("utf-8", errors="replace")
    text = text.strip()
    if not text:
        raise ValueError("Markdown file is empty")

    # Split on ## and ### headings (preserve heading text)
    import re

    sections: list[ParsedSection] = []
    # Pattern: capture heading level and title
    pattern = re.compile(r"^(#{1,6}\s+.+)$", re.MULTILINE)
    splits = pattern.split(text)

    # splits alternates: [before_first_heading, heading1, content1, heading2, content2, ...]
    if len(splits) <= 1:
        # No headings found
        return [ParsedSection(text=text)]

    # Content before first heading
    if splits[0].strip():
        sections.append(ParsedSection(text=splits[0].strip(), section_title="Introduction"))

    # Process heading-content pairs
    for i in range(1, len(splits), 2):
        heading = splits[i].strip()
        content_text = splits[i + 1].strip() if i + 1 < len(splits) else ""
        if content_text:
            # Extract title without # prefix
            title = re.sub(r"^#{1,6}\s+", "", heading)
            full_text = f"{heading}\n\n{content_text}"
            sections.append(ParsedSection(text=full_text, section_title=title))

    return sections if sections else [ParsedSection(text=text)]


def _parse_docx(content: bytes) -> list[ParsedSection]:
    """Parse DOCX using python-docx."""
    from docx import Document

    doc = Document(io.BytesIO(content))
    sections: list[ParsedSection] = []
    current_title: str | None = None
    current_text: list[str] = []

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        # Detect headings by style
        if para.style and "heading" in para.style.name.lower():
            # Save previous section
            if current_text:
                sections.append(
                    ParsedSection(
                        text="\n".join(current_text),
                        section_title=current_title,
                    )
                )
            current_title = text
            current_text = [text]
        else:
            current_text.append(text)

    # Don't forget last section
    if current_text:
        sections.append(
            ParsedSection(
                text="\n".join(current_text),
                section_title=current_title,
            )
        )

    if not sections:
        raise ValueError("DOCX contains no extractable text")

    return sections


def _parse_csv(content: bytes) -> list[ParsedSection]:
    """Parse CSV, converting each row to a text line."""
    text = content.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))

    rows: list[str] = []
    for row in reader:
        if row:
            rows.append(" | ".join(row))

    if not rows:
        raise ValueError("CSV file is empty")

    return [ParsedSection(text="\n".join(rows))]


def _parse_json(content: bytes) -> list[ParsedSection]:
    """Parse JSON, converting to readable text."""
    text = content.decode("utf-8", errors="replace")
    data = json.loads(text)

    # Flatten to readable text
    readable = json.dumps(data, indent=2, ensure_ascii=False)
    return [ParsedSection(text=readable)]
