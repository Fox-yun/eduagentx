"""Deterministic PPTX generation service.

Generates PowerPoint presentations from unit content WITHOUT using LLM.
Extracts content structure (introduction, objectives, sections, practice tasks)
and creates slides deterministically.
"""

from __future__ import annotations

from typing import Any

import structlog

from app.services.presentation_text import extract_presentation_title

try:
    from pptx import Presentation
    from pptx.enum.text import MSO_AUTO_SIZE
    from pptx.presentation import Presentation as PresentationType

    PPTX_AVAILABLE = True
except ImportError:
    PPTX_AVAILABLE = False

logger = structlog.get_logger()


class PPTXGenerator:
    """Deterministic PowerPoint presentation generator."""

    # Slide content limits
    _MAX_SECTION_SLIDES = 5
    _MAX_SECTION_LINES_PER_SLIDE = 6
    _MAX_OBJECTIVE_BULLETS = 6
    _MAX_TASK_BULLETS = 5

    @classmethod
    def generate_pptx_bytes(
        cls,
        unit_content: dict[str, Any],
    ) -> bytes | None:
        """Generate PPTX file bytes from unit content.

        Args:
            unit_content: Dictionary containing unit content with fields:
                - introduction: Course introduction text
                - objectives: List of learning objectives
                - sections: List of section dictionaries with title and content
                - practice_tasks: List of practice task descriptions
                - summary: Course summary text

        Returns:
            PPTX file as bytes, or None if python-pptx is not available.
        """
        if not PPTX_AVAILABLE:
            logger.warning("python-pptx not available, cannot generate PPTX")
            return None

        try:
            prs = Presentation()

            # Title slide
            cls._add_title_slide(prs, unit_content)

            # Objectives slide
            objectives = unit_content.get("objectives", [])
            if objectives:
                cls._add_objectives_slide(prs, objectives)

            # Section slides
            sections = unit_content.get("sections", [])
            cls._add_section_slides(prs, sections)

            # Practice tasks slide
            tasks = unit_content.get("practice_tasks", [])
            if tasks:
                cls._add_practice_tasks_slide(prs, tasks)

            # Summary slide
            summary = unit_content.get("summary")
            if summary:
                cls._add_summary_slide(prs, summary)

            # Save to bytes
            from io import BytesIO

            buffer = BytesIO()
            prs.save(buffer)
            buffer.seek(0)
            return buffer.getvalue()
        except Exception as e:
            logger.error("pptx_generation_failed", error=str(e))
            return None

    @classmethod
    def _add_title_slide(
        cls,
        prs: PresentationType,
        unit_content: dict[str, Any],
    ) -> None:
        """Add title slide with course title and introduction."""
        intro_text = unit_content.get("introduction", "").strip("# \n")
        title = extract_presentation_title(unit_content, fallback="课程内容")

        slide_layout = prs.slide_layouts[0]  # Title slide layout
        slide = prs.slides.add_slide(slide_layout)

        title_shape = slide.shapes.title
        title_shape.text = title
        title_shape.text_frame.word_wrap = True
        title_shape.text_frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE

        # Add introduction as subtitle if available
        if len(intro_text.split("\n")) > 1:
            subtitle = "\n".join(intro_text.split("\n")[1:3])  # First 2-3 lines
            for shape in slide.placeholders:
                if shape.placeholder_format.idx == 1:  # Subtitle
                    shape.text = subtitle[:200]
                    break

    @classmethod
    def _add_objectives_slide(
        cls,
        prs: PresentationType,
        objectives: list[str],
    ) -> None:
        """Add slide with learning objectives as bullet points."""
        slide_layout = prs.slide_layouts[1]  # Title and Content layout
        slide = prs.slides.add_slide(slide_layout)

        # Title
        title_shape = slide.shapes.title
        title_shape.text = "学习目标"

        # Bullets
        if slide.placeholders:
            body = slide.placeholders[1].text_frame
            for i, obj in enumerate(objectives[: cls._MAX_OBJECTIVE_BULLETS]):
                if i == 0:
                    body.text = f"• {obj}"
                else:
                    p = body.add_paragraph()
                    p.text = f"• {obj}"
                    p.level = 0

    @classmethod
    def _add_section_slides(
        cls,
        prs: PresentationType,
        sections: list[dict[str, Any]],
    ) -> None:
        """Add slides for each section, splitting long content."""
        for sec in sections[: cls._MAX_SECTION_SLIDES]:
            sec_title = sec.get("title", "未命名章节")
            sec_content = sec.get("content", "")

            cls._add_section_content_slides(prs, sec_title, sec_content)

    @classmethod
    def _add_section_content_slides(
        cls,
        prs: PresentationType,
        title: str,
        content: str,
    ) -> None:
        """Add one or more slides for section content, splitting if needed."""
        # Clean content: remove markdown headers and bold markers
        lines = []
        for line in content.split("\n"):
            clean = line.strip("# *-[]_").strip()
            if clean:
                lines.append(clean)

        if not lines:
            return

        # Split into chunks for multiple slides
        chunk_size = cls._MAX_SECTION_LINES_PER_SLIDE
        for i in range(0, len(lines), chunk_size):
            chunk = lines[i : i + chunk_size]

            slide_layout = prs.slide_layouts[1]  # Title and Content layout
            slide = prs.slides.add_slide(slide_layout)

            # Title with slide number if multiple
            slide_title = title
            if len(lines) > chunk_size:
                slide_num = i // chunk_size + 1
                total_slides = (len(lines) + chunk_size - 1) // chunk_size
                slide_title = f"{title} ({slide_num}/{total_slides})"

            slide.shapes.title.text = slide_title

            # Content as bullets
            if slide.placeholders:
                body = slide.placeholders[1].text_frame
                body.clear()

                for j, line in enumerate(chunk):
                    if j == 0:
                        body.text = f"• {line[:100]}"
                    else:
                        p = body.add_paragraph()
                        p.text = f"• {line[:100]}"
                        p.level = 0

    @classmethod
    def _add_practice_tasks_slide(
        cls,
        prs: PresentationType,
        tasks: list[Any],
    ) -> None:
        """Add slide with practice tasks."""
        slide_layout = prs.slide_layouts[1]  # Title and Content layout
        slide = prs.slides.add_slide(slide_layout)

        # Title
        title_shape = slide.shapes.title
        title_shape.text = "练习任务"

        # Bullets
        if slide.placeholders:
            body = slide.placeholders[1].text_frame
            body.clear()

            for i, task in enumerate(tasks[: cls._MAX_TASK_BULLETS]):
                desc = str(task.get("description") or task.get("task") or task) if isinstance(task, dict) else str(task)

                if i == 0:
                    body.text = f"• {desc[:100]}"
                else:
                    p = body.add_paragraph()
                    p.text = f"• {desc[:100]}"
                    p.level = 0

    @classmethod
    def _add_summary_slide(
        cls,
        prs: PresentationType,
        summary: str,
    ) -> None:
        """Add summary slide."""
        slide_layout = prs.slide_layouts[1]  # Title and Content layout
        slide = prs.slides.add_slide(slide_layout)

        # Title
        title_shape = slide.shapes.title
        title_shape.text = "课程总结"

        # Content
        if slide.placeholders:
            body = slide.placeholders[1].text_frame
            body.text = summary[:500]  # Truncate if too long

            # Enable word wrap
            body.word_wrap = True
