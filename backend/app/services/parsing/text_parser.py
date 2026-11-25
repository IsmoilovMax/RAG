"""Plain-text parsing with encoding detection."""

from __future__ import annotations

from pathlib import Path

from app.core.exceptions import DocumentParseError
from app.services.parsing.base import ParsedDocument, ParsedSection

_ENCODINGS = ("utf-8-sig", "utf-16", "cp1252", "latin-1")


def decode_bytes(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    if b"\x00" in data[:8192]:
        raise DocumentParseError("File appears to be binary, not text")
    for encoding in _ENCODINGS:
        if encoding == "utf-16":
            continue
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise DocumentParseError("Unable to decode text file")  # pragma: no cover


def read_text_file(path: Path) -> str:
    return decode_bytes(path.read_bytes())


def parse_txt(path: Path) -> ParsedDocument:
    return ParsedDocument(sections=[ParsedSection(text=read_text_file(path))])
