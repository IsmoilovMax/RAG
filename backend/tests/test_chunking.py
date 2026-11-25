"""Text cleaning and chunking."""

from __future__ import annotations

import pytest

from app.services.chunking import chunk_document, make_splitter
from app.services.parsing import ParsedDocument, ParsedSection
from app.services.text_cleaning import clean_text

LOREM = (
    "Retrieval-augmented generation combines search with language models. "
    "Documents are split into chunks. Each chunk is embedded into a vector. "
    "Relevant chunks are retrieved for every question. "
) * 30


def test_clean_text_normalises_whitespace_and_controls():
    raw = "Hello\x00   world\t\t!\r\n\r\n\r\n\r\nNext​ paragraph"
    assert clean_text(raw) == "Hello world !\n\nNext paragraph"


def test_clean_text_fixes_hyphenation_and_wrapped_lines():
    raw = "The robot uses a sophis-\nticated sensor and\nreaches high speed.\n\n- bullet one\n- bullet two"
    cleaned = clean_text(raw)
    assert "sophisticated sensor and reaches high speed." in cleaned
    assert "- bullet one\n- bullet two" in cleaned


def test_clean_text_keeps_wrapped_numbers():
    assert "stipend of 600 euros" in clean_text("stipend of\n600 euros")


def test_clean_text_unicode_normalisation():
    assert clean_text("ﬁle ＡＢＣ") == "file ABC"


def test_clean_text_empty():
    assert clean_text("") == ""


def test_chunks_respect_size_and_overlap():
    doc = ParsedDocument(sections=[ParsedSection(text=LOREM, page=1)])
    chunks = chunk_document(doc, chunk_size=300, chunk_overlap=60)
    assert len(chunks) > 5
    assert all(len(c.text) <= 300 for c in chunks)
    assert [c.index for c in chunks] == list(range(len(chunks)))
    # Consecutive chunks share overlapping text.
    overlaps = sum(1 for a, b in zip(chunks, chunks[1:], strict=False) if b.text[:30] in a.text)
    assert overlaps >= len(chunks) // 2


def test_chunks_never_cross_sections_and_keep_metadata():
    doc = ParsedDocument(
        sections=[
            ParsedSection(text="First page text about leave policy.", page=1),
            ParsedSection(text="Second page text about remote work.", page=2, section="Remote"),
            ParsedSection(text="   ", page=3),
        ]
    )
    chunks = chunk_document(doc, chunk_size=500, chunk_overlap=50)
    assert [(c.page, c.section) for c in chunks] == [(1, None), (2, "Remote")]


def test_tabular_chunks_split_on_rows_without_overlap():
    rows = "\n".join(f"SKU: NW-{i:04d} | Part: Part {i} | Stock: {i * 3}" for i in range(200))
    doc = ParsedDocument(sections=[ParsedSection(text=rows, section="Table")], is_tabular=True)
    chunks = chunk_document(doc, chunk_size=400, chunk_overlap=100)
    assert len(chunks) > 3
    for chunk in chunks:
        for line in chunk.text.split("\n"):
            assert line.startswith("SKU: NW-")  # rows are never cut in half
    all_lines = [line for c in chunks for line in c.text.split("\n")]
    assert len(all_lines) == len(set(all_lines)) == 200  # no duplicated rows


def test_trivial_fragments_are_dropped():
    doc = ParsedDocument(sections=[ParsedSection(text="- -", page=1), ParsedSection(text="Real content here.", page=2)])
    chunks = chunk_document(doc, chunk_size=200, chunk_overlap=0)
    assert [c.text for c in chunks] == ["Real content here."]


@pytest.mark.parametrize(("size", "overlap"), [(0, 0), (100, 100), (100, 150), (100, -1)])
def test_invalid_splitter_parameters(size, overlap):
    with pytest.raises(ValueError):
        make_splitter(size, overlap)


def test_sample_documents_chunk_cleanly(sample_dir):
    from app.services.parsing import detect_file_type, parse_document

    for path in sample_dir.iterdir():
        parsed = parse_document(path, detect_file_type(path.name))
        for s in parsed.sections:
            s.text = clean_text(s.text)
        chunks = chunk_document(parsed, chunk_size=1000, chunk_overlap=150)
        assert chunks, path.name
        assert all(c.text.strip() for c in chunks)
