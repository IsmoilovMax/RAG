"""Semantic retrieval with similarity thresholds and context budgeting."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.services.embeddings import Embedder
from app.services.vector_store import ChromaVectorStore, SearchHit

_WS = re.compile(r"\s+")


@dataclass(slots=True)
class RetrievedChunk:
    id: str
    text: str
    similarity: float
    document_id: str
    filename: str
    file_type: str | None = None
    page: int | None = None
    section: str | None = None
    chunk_index: int | None = None

    @classmethod
    def from_hit(cls, hit: SearchHit) -> RetrievedChunk:
        meta = hit.metadata
        return cls(
            id=hit.id,
            text=hit.text,
            similarity=hit.similarity,
            document_id=str(meta.get("document_id", "")),
            filename=str(meta.get("filename", "unknown")),
            file_type=meta.get("file_type"),
            page=meta.get("page"),
            section=meta.get("section"),
            chunk_index=meta.get("chunk_index"),
        )

    def location(self) -> str:
        parts = [self.filename]
        if self.section:
            parts.append(self.section)
        elif self.page is not None:
            parts.append(f"page {self.page}")
        if self.section and self.page is not None and self.file_type == "pdf":
            parts.append(f"page {self.page}")
        return " — ".join(parts)


@dataclass(slots=True)
class RetrievalResult:
    chunks: list[RetrievedChunk] = field(default_factory=list)
    best_similarity: float | None = None
    candidates: int = 0
    rejected_below_threshold: int = 0
    relaxed: bool = False  # threshold relaxed because the user scoped the question to documents

    def as_debug(self) -> dict[str, Any]:
        return {
            "best_similarity": self.best_similarity,
            "candidates": self.candidates,
            "rejected_below_threshold": self.rejected_below_threshold,
            "used": len(self.chunks),
            "relaxed": self.relaxed,
        }


def _fingerprint(text: str) -> str:
    return _WS.sub(" ", text.lower()).strip()[:300]


class Retriever:
    def __init__(self, embedder: Embedder, store: ChromaVectorStore) -> None:
        self.embedder = embedder
        self.store = store

    def opening_chunks(self, query: str, document_ids: list[str]) -> list[RetrievedChunk]:
        """First chunk of each document (title, author, name, topic), scored against the query."""
        vector = self.embedder.embed_query(query)
        chunks: list[RetrievedChunk] = []
        for doc_id in document_ids:
            hits = self.store.search(vector, limit=1, document_ids=[doc_id], chunk_index=0)
            chunks.extend(RetrievedChunk.from_hit(h) for h in hits)
        return chunks

    def retrieve(
        self,
        query: str,
        *,
        top_k: int,
        similarity_threshold: float,
        relative_cutoff: float,
        max_context_chars: int,
        document_ids: list[str] | None = None,
        extra_queries: list[str] | None = None,
    ) -> RetrievalResult:
        candidate_limit = max(top_k * 4, 20)
        merged: dict[str, SearchHit] = {}
        for q in [query, *(extra_queries or [])]:
            if not q.strip():
                continue
            vector = self.embedder.embed_query(q)
            for hit in self.store.search(vector, limit=candidate_limit, document_ids=document_ids):
                current = merged.get(hit.id)
                if current is None or hit.similarity > current.similarity:
                    merged[hit.id] = hit

        ranked = sorted(merged.values(), key=lambda h: h.similarity, reverse=True)
        result = RetrievalResult(candidates=len(ranked))
        if not ranked:
            return result
        result.best_similarity = ranked[0].similarity

        # 1) absolute threshold, 2) relative cutoff from the best match.
        passing = [h for h in ranked if h.similarity >= similarity_threshold]
        result.rejected_below_threshold = len(ranked) - len(passing)
        if not passing:
            return result
        floor = passing[0].similarity - relative_cutoff
        passing = [h for h in passing if h.similarity >= floor]

        # 3) de-duplicate near-identical chunks, 4) respect the context budget.
        seen: set[str] = set()
        used_chars = 0
        for hit in passing:
            fp = _fingerprint(hit.text)
            if fp in seen:
                continue
            if result.chunks and used_chars + len(hit.text) > max_context_chars:
                break
            seen.add(fp)
            used_chars += len(hit.text)
            result.chunks.append(RetrievedChunk.from_hit(hit))
            if len(result.chunks) >= top_k:
                break
        return result
