"""PDF parsing via PyMuPDF."""

from __future__ import annotations

from pathlib import Path

import pymupdf

from app.core.exceptions import DocumentParseError
from app.services.parsing.base import ParsedDocument, ParsedSection


def parse_pdf(path: Path) -> ParsedDocument:
    try:
        doc = pymupdf.open(path)
    except Exception as exc:  # pymupdf raises various internal errors
        raise DocumentParseError(f"Could not open PDF: {exc}") from exc

    with doc:
        if doc.needs_pass:
            raise DocumentParseError("PDF is password-protected and cannot be read")
        sections: list[ParsedSection] = []
        for index, page in enumerate(doc, start=1):
            try:
                text = page.get_text("text", sort=True)
            except Exception as exc:
                raise DocumentParseError(f"Failed to read page {index}: {exc}") from exc
            sections.append(ParsedSection(text=text, page=index))
        return ParsedDocument(sections=sections, page_count=doc.page_count)
