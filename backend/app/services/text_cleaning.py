"""Text normalisation applied to extracted document text before chunking."""

from __future__ import annotations

import re
import unicodedata

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‏﻿]")
_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")
_MULTI_SPACE = re.compile(r"[ \t ]+")
_MULTI_NEWLINE = re.compile(r"\n{3,}")
_SENTENCE_END = re.compile(r"[.!?:;\"')\]]$")
_LIST_START = re.compile(r"^(\s*[-*•▪◦‣]|\s*\d+[.)]|\s*[a-zA-Z][.)]\s)")


def _merge_wrapped_lines(text: str) -> str:
    """Join hard-wrapped lines (common in PDFs) while keeping lists and paragraphs."""
    lines = text.split("\n")
    merged: list[str] = []
    for line in lines:
        stripped = line.strip()
        if (
            merged
            and stripped
            and merged[-1]
            and not _SENTENCE_END.search(merged[-1])
            and not _LIST_START.match(stripped)
            and (stripped[0].islower() or stripped[0].isdigit())
        ):
            merged[-1] = f"{merged[-1]} {stripped}"
        else:
            merged.append(stripped)
    return "\n".join(merged)


def clean_text(text: str, *, merge_lines: bool = True) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_CHARS.sub("", text)
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    text = "\n".join(_MULTI_SPACE.sub(" ", line).strip() for line in text.split("\n"))
    if merge_lines:
        text = _merge_wrapped_lines(text)
    text = _MULTI_NEWLINE.sub("\n\n", text)
    return text.strip()
