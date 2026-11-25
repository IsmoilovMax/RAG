"""PowerPoint parsing via python-pptx (text frames, tables, grouped shapes and notes)."""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from app.core.exceptions import DocumentParseError
from app.services.parsing.base import ParsedDocument, ParsedSection, format_row


def _shape_lines(shape) -> list[str]:
    lines: list[str] = []
    if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
        for child in shape.shapes:
            lines.extend(_shape_lines(child))
        return lines
    if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
        for paragraph in shape.text_frame.paragraphs:
            text = "".join(run.text for run in paragraph.runs).strip()
            if text:
                lines.append(text)
    if getattr(shape, "has_table", False) and shape.has_table:
        rows = [[cell.text for cell in row.cells] for row in shape.table.rows]
        if rows:
            headers, body = rows[0], rows[1:]
            lines.extend(line for row in body if (line := format_row(headers, row)))
    return lines


def parse_pptx(path: Path) -> ParsedDocument:
    try:
        presentation = Presentation(str(path))
    except Exception as exc:
        raise DocumentParseError(f"Could not open PPTX: {exc}") from exc

    sections: list[ParsedSection] = []
    for index, slide in enumerate(presentation.slides, start=1):
        lines: list[str] = []
        title = None
        if slide.shapes.title is not None and slide.shapes.title.has_text_frame:
            title = slide.shapes.title.text_frame.text.strip() or None
        for shape in slide.shapes:
            lines.extend(_shape_lines(shape))
        if slide.has_notes_slide:
            notes = slide.notes_slide.notes_text_frame
            if notes is not None and notes.text.strip():
                lines.append(f"Speaker notes: {notes.text.strip()}")
        label = f"Slide {index}" + (f": {title}" if title else "")
        sections.append(ParsedSection(text="\n".join(lines), page=index, section=label))
    return ParsedDocument(sections=sections, page_count=len(presentation.slides))
