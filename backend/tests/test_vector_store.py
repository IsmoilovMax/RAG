"""ChromaDB vector store wrapper."""

from __future__ import annotations

import pytest

from app.services.vector_store import ChromaVectorStore, VectorRecord


@pytest.fixture
def store(tmp_path) -> ChromaVectorStore:
    return ChromaVectorStore(tmp_path / "chroma", "unit-test")


def rec(id_: str, vec: list[float], doc: str, index: int = 0, **meta) -> VectorRecord:
    return VectorRecord(
        id=id_,
        text=f"text of {id_}",
        embedding=vec,
        metadata={"document_id": doc, "chunk_index": index, "filename": f"{doc}.txt", **meta},
    )


def test_search_ranks_by_cosine_similarity(store):
    store.add([rec("a", [1, 0, 0], "d1"), rec("b", [0.7, 0.7, 0], "d1", 1), rec("c", [0, 0, 1], "d2")])
    hits = store.search([1, 0, 0], limit=3)
    assert [h.id for h in hits] == ["a", "b", "c"]
    assert hits[0].similarity == pytest.approx(1.0, abs=1e-3)
    assert hits[1].similarity == pytest.approx(0.7071, abs=1e-3)
    assert hits[2].similarity == pytest.approx(0.0, abs=1e-3)
    assert hits[0].metadata["filename"] == "d1.txt"


def test_search_filters_by_document(store):
    store.add([rec("a", [1, 0], "d1"), rec("b", [1, 0.1], "d2"), rec("c", [1, 0.2], "d3")])
    assert {h.id for h in store.search([1, 0], limit=5, document_ids=["d2"])} == {"b"}
    assert {h.id for h in store.search([1, 0], limit=5, document_ids=["d2", "d3"])} == {"b", "c"}


def test_none_metadata_is_dropped(store):
    store.add([rec("a", [1, 0], "d1", page=None, section=None)])
    meta = store.search([1, 0], limit=1)[0].metadata
    assert "page" not in meta and "section" not in meta


def test_upsert_is_idempotent_and_delete_by_document(store):
    store.add([rec("a", [1, 0], "d1"), rec("b", [0, 1], "d2")])
    store.add([rec("a", [1, 0], "d1")])
    assert store.count() == 2
    store.delete_document("d1")
    assert store.count() == 1
    assert [h.id for h in store.search([1, 0], limit=5)] == ["b"]


def test_empty_store_search(store):
    assert store.search([1, 0], limit=5) == []


def test_document_chunks_are_ordered(store):
    store.add([rec(f"x{i}", [1, i], "d1", index=i) for i in (3, 1, 2, 0)])
    rows = store.get_document_chunks("d1", limit=3)
    assert [r["metadata"]["chunk_index"] for r in rows] == [0, 1, 2]


def test_large_batches(store):
    records = [rec(f"r{i}", [1.0, float(i % 7)], "big", index=i) for i in range(2500)]
    store.add(records)
    assert store.count() == 2500


def test_persistence(tmp_path):
    path = tmp_path / "persist"
    ChromaVectorStore(path, "persist-test").add([rec("a", [1, 0], "d1")])
    assert ChromaVectorStore(path, "persist-test").count() == 1
