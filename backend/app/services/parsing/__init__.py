"""Document parser registry and file-type validation."""

from __future__ import annotations

import zipfile
from pathlib import Path

from app.core.exceptions import DocumentParseError, ValidationError
from app.services.parsing.base import ParsedDocument, ParsedSection, Parser
from app.services.parsing.docx_parser import parse_docx
from app.services.parsing.pdf_parser import parse_pdf
from app.services.parsing.pptx_parser import parse_pptx
from app.services.parsing.spreadsheet_parser import parse_csv, parse_xlsx
from app.services.parsing.text_parser import decode_bytes, parse_txt

__all__ = [
    "SUPPORTED_TYPES",
    "ParsedDocument",
    "ParsedSection",
    "detect_file_type",
    "parse_document",
    "validate_content",
]

# extension -> (mime type, parser)
SUPPORTED_TYPES: dict[str, tuple[str, Parser]] = {
    "pdf": ("application/pdf", parse_pdf),
    "docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        parse_docx,
    ),
    "txt": ("text/plain", parse_txt),
    "md": ("text/markdown", parse_txt),
    "csv": ("text/csv", parse_csv),
    "xlsx": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        parse_xlsx,
    ),
    "pptx": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        parse_pptx,
    ),
}

# Office Open XML containers must include this part.
_OOXML_REQUIRED_PART = {
    "docx": "word/document.xml",
    "xlsx": "xl/workbook.xml",
    "pptx": "ppt/presentation.xml",
}


def detect_file_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower().lstrip(".")
    if suffix not in SUPPORTED_TYPES:
        allowed = ", ".join(sorted(SUPPORTED_TYPES))
        raise ValidationError(f"Unsupported file type '.{suffix}'. Allowed: {allowed}")
    return suffix


def validate_content(path: Path, file_type: str) -> None:
    """Verify the file's bytes match its claimed type (magic-number check)."""
    with path.open("rb") as fh:
        head = fh.read(8192)
    if not head:
        raise ValidationError("File is empty")

    if file_type == "pdf":
        if b"%PDF-" not in head[:1024]:
            raise ValidationError("File content is not a valid PDF")
    elif file_type in _OOXML_REQUIRED_PART:
        if not head.startswith(b"PK\x03\x04"):
            raise ValidationError(f"File content is not a valid .{file_type} document")
        try:
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
        except zipfile.BadZipFile as exc:
            raise ValidationError(f"Corrupted .{file_type} archive") from exc
        if _OOXML_REQUIRED_PART[file_type] not in names:
            raise ValidationError(f"File content is not a valid .{file_type} document")
    else:  # text formats
        try:
            decode_bytes(head)
        except DocumentParseError as exc:
            raise ValidationError(exc.message) from exc


def parse_document(path: Path, file_type: str) -> ParsedDocument:
    try:
        _, parser = SUPPORTED_TYPES[file_type]
    except KeyError as exc:
        raise DocumentParseError(f"No parser for type '{file_type}'") from exc
    try:
        return parser(path)
    except DocumentParseError:
        raise
    except Exception as exc:  # malformed documents surface as parse errors
        raise DocumentParseError(f"Failed to parse document: {exc}") from exc
