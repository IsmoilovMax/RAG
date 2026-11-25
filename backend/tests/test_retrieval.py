"""Retrieval logic (thresholds, cutoffs, budget) and real-model retrieval accuracy."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.services.retrieval import Retriever
from app.services.vector_store import ChromaVectorStore, VectorRecord
from scripts.generate_samples import EXAMPLE_QUESTIONS, UNANSWERABLE_QUESTIONS
from tests.conftest import add_document, make_settings


class StaticEmbedder:
    """Maps known query strings to fixed vectors."""

    model_name = "static"
    is_loaded = True
    dimension = 3

    def __init__(self, mapping):
        self.mapping = mapping

    def embed_query(self, text):
        return self.mapping[text]

    def embed_documents(self, texts):
        return [self.mapping[t] for t in texts]


def _store(tmp_path, rows):
    store = ChromaVectorStore(tmp_path / "chroma", "retrieval-unit")
    store.add(
        [
            VectorRecord(id=i, text=text, embedding=vec, metadata={"document_id": doc, "filename": f"{doc}.txt", "chunk_index": n})
            for n, (i, text, vec, doc) in enumerate(rows)
        ]
    )
    return store


def _retrieve(retriever, q="q", **kw):
    params = {"top_k": 5, "similarity_threshold": 0.5, "relative_cutoff": 1.0, "max_context_chars": 10_000}
    params.update(kw)
    return retriever.retrieve(q, **params)


def test_threshold_filters_irrelevant_chunks(tmp_path):
    store = _store(tmp_path, [("a", "relevant", [1, 0, 0], "d1"), ("b", "weak", [0.3, 0.95, 0], "d1"), ("c", "off", [0, 0, 1], "d2")])
    r = _retrieve(Retriever(StaticEmbedder({"q": [1, 0, 0]}), store))
    assert [c.id for c in r.chunks] == ["a"]
    assert r.best_similarity == pytest.approx(1.0, abs=1e-3)
    assert r.rejected_below_threshold == 2


def test_nothing_above_threshold_returns_empty(tmp_path):
    store = _store(tmp_path, [("a", "x", [0, 1, 0], "d1")])
    r = _retrieve(Retriever(StaticEmbedder({"q": [1, 0, 0]}), store))
    assert r.chunks == []
    assert r.best_similarity is not None and r.best_similarity < 0.5


def test_relative_cutoff_drops_much_weaker_matches(tmp_path):
    store = _store(tmp_path, [("a", "best", [1, 0, 0], "d1"), ("b", "ok", [0.8, 0.6, 0], "d1"), ("c", "close", [0.98, 0.2, 0], "d1")])
    r = _retrieve(Retriever(StaticEmbedder({"q": [1, 0, 0]}), store), relative_cutoff=0.1)
    assert [c.id for c in r.chunks] == ["a", "c"]


def test_top_k_dedup_and_context_budget(tmp_path):
    rows = [
        ("a", "same text", [1, 0, 0], "d1"),
        ("b", "Same   TEXT", [0.99, 0.1, 0], "d2"),
        ("c", "x" * 400, [0.97, 0.2, 0], "d1"),
        ("d", "y" * 400, [0.96, 0.25, 0], "d1"),
    ]
    retriever = Retriever(StaticEmbedder({"q": [1, 0, 0]}), _store(tmp_path, rows))
    r = _retrieve(retriever)
    assert [c.id for c in r.chunks] == ["a", "c", "d"]  # "b" is a duplicate of "a"
    assert [c.id for c in _retrieve(retriever, top_k=2).chunks] == ["a", "c"]
    assert [c.id for c in _retrieve(retriever, max_context_chars=500).chunks] == ["a", "c"]


def test_document_filter_and_extra_queries(tmp_path):
    rows = [("a", "alpha", [1, 0, 0], "d1"), ("b", "beta", [0, 1, 0], "d2")]
    retriever = Retriever(StaticEmbedder({"q": [1, 0, 0], "follow": [0, 1, 0]}), _store(tmp_path, rows))
    assert [c.id for c in _retrieve(retriever, document_ids=["d2"], similarity_threshold=0.0).chunks] == ["b"]
    merged = _retrieve(retriever, extra_queries=["follow"], relative_cutoff=1.0)
    assert {c.id for c in merged.chunks} == {"a", "b"}


# ----------------------------------------------------------- real-model accuracy
@pytest.fixture(scope="module")
def real_container(tmp_path_factory):
    from app.container import build_container
    from scripts.generate_samples import generate

    tmp = tmp_path_factory.mktemp("accuracy")
    settings: Settings = make_settings(tmp, similarity_threshold=0.55, relative_score_cutoff=0.12)
    container = build_container(settings, llm=None)
    try:
        container.embedder.warmup()
    except Exception as exc:  # pragma: no cover - offline
        pytest.skip(f"Embedding model unavailable: {exc}")
    for path in generate(tmp / "samples").values():
        add_document(container, path)
    yield container
    container.ingestion.shutdown()


@pytest.mark.model
def test_all_sample_documents_indexed(real_container):
    from sqlalchemy import select

    from app.db.models import Document, DocumentStatus

    with real_container.db.session() as s:
        docs = s.scalars(select(Document)).all()
    assert len(docs) == 6
    assert all(d.status == DocumentStatus.READY and d.chunk_count > 0 for d in docs), [
        (d.filename, d.status, d.error_message) for d in docs
    ]


@pytest.mark.model
@pytest.mark.parametrize(("question", "source", "fact"), EXAMPLE_QUESTIONS)
def test_retrieval_accuracy(real_container, question, source, fact):
    s = real_container.settings
    result = real_container.rag.retriever.retrieve(
        question,
        top_k=s.retrieval_top_k,
        similarity_threshold=s.similarity_threshold,
        relative_cutoff=s.relative_score_cutoff,
        max_context_chars=s.max_context_chars,
    )
    assert result.chunks, f"nothing retrieved for {question!r} (best={result.best_similarity})"
    top = result.chunks[0]
    assert top.filename == source
    assert fact.lower() in " ".join(c.text for c in result.chunks).lower()


@pytest.mark.model
@pytest.mark.parametrize("question", UNANSWERABLE_QUESTIONS)
def test_unanswerable_questions_retrieve_nothing(real_container, question):
    s = real_container.settings
    result = real_container.rag.retriever.retrieve(
        question,
        top_k=s.retrieval_top_k,
        similarity_threshold=s.similarity_threshold,
        relative_cutoff=s.relative_score_cutoff,
        max_context_chars=s.max_context_chars,
    )
    assert result.chunks == [], [(c.filename, c.similarity) for c in result.chunks]


@pytest.mark.model
def test_page_numbers_are_returned_for_pdf(real_container):
    s = real_container.settings
    result = real_container.rag.retriever.retrieve(
        "remote work days per week", top_k=3, similarity_threshold=s.similarity_threshold,
        relative_cutoff=s.relative_score_cutoff, max_context_chars=s.max_context_chars,
    )
    top = result.chunks[0]
    assert top.filename == "employee_handbook.pdf" and top.page == 3
