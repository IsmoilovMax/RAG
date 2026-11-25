"""Embedding generation with the real BAAI/bge-small-en-v1.5 model (CPU)."""

from __future__ import annotations

import math

import pytest

from app.core.config import Settings
from app.services.embeddings import SentenceTransformerEmbedder

pytestmark = pytest.mark.model


@pytest.fixture(scope="session")
def embedder() -> SentenceTransformerEmbedder:
    s = Settings(_env_file=None)
    emb = SentenceTransformerEmbedder(
        s.embedding_model, batch_size=8, query_instruction=s.embedding_query_instruction
    )
    try:
        emb.warmup()
    except Exception as exc:  # pragma: no cover - offline environments
        pytest.skip(f"Embedding model unavailable: {exc}")
    return emb


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_model_runs_on_cpu_with_expected_dimension(embedder):
    assert embedder.dimension == 384
    assert str(embedder._model.device) == "cpu"


def test_vectors_are_normalised(embedder):
    vectors = embedder.embed_documents(["hello world", "another sentence"])
    for vec in vectors:
        assert len(vec) == 384
        assert math.isclose(math.sqrt(_dot(vec, vec)), 1.0, rel_tol=1e-3)


def test_batching_matches_single_encoding(embedder):
    texts = [f"Sentence number {i} about warehouse robots." for i in range(20)]
    batched = embedder.embed_documents(texts)
    single = [embedder.embed_documents([t])[0] for t in texts[:3]]
    for a, b in zip(batched[:3], single, strict=True):
        assert _dot(a, b) > 0.999


def test_empty_input_returns_empty(embedder):
    assert embedder.embed_documents([]) == []


def test_semantic_similarity_ordering(embedder):
    query = embedder.embed_query("How many vacation days do employees get?")
    relevant, irrelevant = embedder.embed_documents(
        [
            "Every full-time employee receives 28 days of paid annual leave per year.",
            "The robot's LiDAR sensor has a range of 30 metres.",
        ]
    )
    assert _dot(query, relevant) > _dot(query, irrelevant) + 0.1


def test_model_is_loaded_once(embedder):
    model = embedder._model
    embedder.embed_query("again")
    embedder.warmup()
    assert embedder._model is model
