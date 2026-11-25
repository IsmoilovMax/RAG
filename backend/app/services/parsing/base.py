"""Common types for document parsers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(slots=True)
class ParsedSection:
    """A logical unit of a document (PDF page, slide, sheet, DOCX heading section…)."""

    text: str
    page: int | None = None  # 1-based page / slide / sheet number when meaningful
    section: str | None = None  # Human-readable label, e.g. "Sheet: Sales"


@dataclass(slots=True)
class ParsedDocument:
    sections: list[ParsedSection] = field(default_factory=list)
    page_count: int | None = None
    is_tabular: bool = False

    @property
    def char_count(self) -> int:
        return sum(len(s.text) for s in self.sections)

    @property
    def has_text(self) -> bool:
        return any(s.text.strip() for s in self.sections)


class Parser(Protocol):
    def __call__(self, path: Path) -> ParsedDocument: ...


def format_row(headers: list[str], values: list[str]) -> str:
    """Render a table row as a self-describing line: "Header: value | Header: value"."""
    parts: list[str] = []
    for idx, value in enumerate(values):
        value = value.strip()
        if not value:
            continue
        header = headers[idx].strip() if idx < len(headers) and headers[idx] else ""
        parts.append(f"{header}: {value}" if header else value)
    return " | ".join(parts)


def cell_to_str(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).replace("\n", " ").strip()
