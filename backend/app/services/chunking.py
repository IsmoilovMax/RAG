"""Structure-aware chunking built on LangChain's recursive character splitter."""

from __future__ import annotations

from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.services.parsing.base import ParsedDocument

MIN_CHUNK_CHARS = 20

# Paragraphs first, then lines, then sentences, then words.
_SEPARATORS = ["\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " ", ""]


@dataclass(slots=True)
class Chunk:
    text: str
    index: int
    page: int | None = None
    section: str | None = None


def make_splitter(chunk_size: int, chunk_overlap: int) -> RecursiveCharacterTextSplitter:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if not 0 <= chunk_overlap < chunk_size:
        raise ValueError("chunk_overlap must be >= 0 and smaller than chunk_size")
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=_SEPARATORS,
        keep_separator="end",
        strip_whitespace=True,
    )


def chunk_document(
    document: ParsedDocument, *, chunk_size: int, chunk_overlap: int
) -> list[Chunk]:
    """Split each section independently so chunks never straddle pages/slides/sheets.

    Tabular content is split on row boundaries with no overlap (rows are
    self-describing, so overlap would only duplicate data).
    """
    splitter = make_splitter(chunk_size, chunk_overlap)
    row_splitter = (
        make_splitter(chunk_size, 0) if document.is_tabular else splitter
    )
    chunks: list[Chunk] = []
    for section in document.sections:
        if not section.text.strip():
            continue
        active = row_splitter if document.is_tabular else splitter
        for piece in active.split_text(section.text):
            piece = piece.strip()
            if len(piece) < MIN_CHUNK_CHARS and not any(ch.isalnum() for ch in piece):
                continue
            if len(piece.replace(" ", "")) < 3:
                continue
            chunks.append(
                Chunk(
                    text=piece,
                    index=len(chunks),
                    page=section.page,
                    section=section.section,
                )
            )
    return chunks
