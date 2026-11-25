"""CSV and XLSX parsing. Rows become self-describing "Header: value" lines."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from openpyxl import load_workbook

from app.core.exceptions import DocumentParseError
from app.services.parsing.base import (
    ParsedDocument,
    ParsedSection,
    cell_to_str,
    format_row,
)
from app.services.parsing.text_parser import read_text_file

MAX_ROWS_PER_SHEET = 200_000


def _rows_to_text(rows: list[list[str]]) -> str:
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        return ""
    headers, body = rows[0], rows[1:]
    if not body:
        return " | ".join(h for h in headers if h.strip())
    return "\n".join(line for row in body if (line := format_row(headers, row)))


def parse_csv(path: Path) -> ParsedDocument:
    raw = read_text_file(path)
    try:
        sample = raw[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        rows = list(csv.reader(io.StringIO(raw), dialect))
    except csv.Error as exc:
        raise DocumentParseError(f"Malformed CSV: {exc}") from exc
    return ParsedDocument(
        sections=[ParsedSection(text=_rows_to_text(rows), section="Table")],
        is_tabular=True,
    )


def parse_xlsx(path: Path) -> ParsedDocument:
    try:
        workbook = load_workbook(filename=str(path), read_only=True, data_only=True)
    except Exception as exc:
        raise DocumentParseError(f"Could not open XLSX: {exc}") from exc

    sections: list[ParsedSection] = []
    try:
        for index, sheet in enumerate(workbook.worksheets, start=1):
            rows: list[list[str]] = []
            for row_idx, row in enumerate(sheet.iter_rows(values_only=True)):
                if row_idx >= MAX_ROWS_PER_SHEET:
                    break
                rows.append([cell_to_str(v) for v in row])
            text = _rows_to_text(rows)
            if text:
                sections.append(
                    ParsedSection(text=text, page=index, section=f"Sheet: {sheet.title}")
                )
        sheet_count = len(workbook.worksheets)
    finally:
        workbook.close()
    return ParsedDocument(sections=sections, page_count=sheet_count, is_tabular=True)
