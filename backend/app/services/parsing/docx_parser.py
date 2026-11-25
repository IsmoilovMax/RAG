"""DOCX parsing via python-docx (paragraphs and tables in document order)."""

from __future__ import annotations

from pathlib import Path

import docx
from docx.document import Document as DocxDocument
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.core.exceptions import DocumentParseError
from app.services.parsing.base import ParsedDocument, ParsedSection, format_row


def _iter_blocks(document: DocxDocument):
    body = document.element.body
    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            yield Paragraph(child, document)
        elif tag == "tbl":
            yield Table(child, document)


def _table_lines(table: Table) -> list[str]:
    rows = [[cell.text for cell in row.cells] for row in table.rows]
    if not rows:
        return []
    headers, body = rows[0], rows[1:]
    if not body:
        return [" | ".join(c for c in headers if c.strip())]
    return [line for row in body if (line := format_row(headers, row))]


def parse_docx(path: Path) -> ParsedDocument:
    try:
        document = docx.Document(str(path))
    except Exception as exc:
        raise DocumentParseError(f"Could not open DOCX: {exc}") from exc

    sections: list[ParsedSection] = []
    current_heading: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            sections.append(ParsedSection(text="\n".join(buffer), section=current_heading))
            buffer.clear()

    for block in _iter_blocks(document):
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if not text:
                continue
            style = (block.style.name or "").lower() if block.style is not None else ""
            if style.startswith("heading") or style == "title":
                flush()
                current_heading = text[:200]
            buffer.append(text)
        else:
            buffer.extend(_table_lines(block))
    flush()
    return ParsedDocument(sections=sections)
