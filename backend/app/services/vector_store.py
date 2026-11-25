"""ChromaDB vector store wrapper."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

logger = logging.getLogger(__name__)

# Chroma rejects very large single batches; stay comfortably below its limit.
_UPSERT_BATCH = 1000


@dataclass(slots=True)
class VectorRecord:
    id: str
    text: str
    embedding: list[float]
    metadata: dict[str, Any]


@dataclass(slots=True)
class SearchHit:
    id: str
    text: str
    similarity: float
    metadata: dict[str, Any] = field(default_factory=dict)


def _clean_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Chroma metadata values must be str/int/float/bool and non-null."""
    return {
        k: v for k, v in metadata.items() if v is not None and isinstance(v, (str, int, float, bool))
    }


class ChromaVectorStore:
    def __init__(self, persist_dir: Path | None, collection_name: str) -> None:
        chroma_settings = ChromaSettings(anonymized_telemetry=False, allow_reset=False)
        if persist_dir is None:
            self._client = chromadb.EphemeralClient(settings=chroma_settings)
        else:
            persist_dir.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=str(persist_dir), settings=chroma_settings
            )
        self.collection_name = collection_name
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
            embedding_function=None,  # embeddings are always supplied by us
        )

    def add(self, records: list[VectorRecord]) -> None:
        for start in range(0, len(records), _UPSERT_BATCH):
            batch = records[start : start + _UPSERT_BATCH]
            self._collection.upsert(
                ids=[r.id for r in batch],
                embeddings=[r.embedding for r in batch],
                documents=[r.text for r in batch],
                metadatas=[_clean_metadata(r.metadata) for r in batch],
            )

    def delete_document(self, document_id: str) -> None:
        self._collection.delete(where={"document_id": document_id})

    def search(
        self,
        embedding: list[float],
        *,
        limit: int,
        document_ids: list[str] | None = None,
        chunk_index: int | None = None,
    ) -> list[SearchHit]:
        total = self.count()
        if total == 0:
            return []
        clauses: list[dict[str, Any]] = []
        if document_ids:
            clauses.append(
                {"document_id": document_ids[0]}
                if len(document_ids) == 1
                else {"document_id": {"$in": list(document_ids)}}
            )
        if chunk_index is not None:
            clauses.append({"chunk_index": chunk_index})
        where: dict[str, Any] | None = None
        if len(clauses) == 1:
            where = clauses[0]
        elif clauses:
            where = {"$and": clauses}
        result = self._collection.query(
            query_embeddings=[embedding],
            n_results=min(limit, total),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        hits: list[SearchHit] = []
        ids = result.get("ids") or [[]]
        for idx, hit_id in enumerate(ids[0]):
            distance = float(result["distances"][0][idx])
            hits.append(
                SearchHit(
                    id=hit_id,
                    text=result["documents"][0][idx] or "",
                    similarity=round(1.0 - distance, 4),  # cosine distance -> similarity
                    metadata=dict(result["metadatas"][0][idx] or {}),
                )
            )
        return hits

    def get_document_chunks(
        self, document_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        result = self._collection.get(
            where={"document_id": document_id},
            include=["documents", "metadatas"],
        )
        rows = [
            {"id": cid, "text": text, "metadata": meta or {}}
            for cid, text, meta in zip(
                result["ids"], result["documents"], result["metadatas"], strict=False
            )
        ]
        rows.sort(key=lambda r: r["metadata"].get("chunk_index", 0))
        return rows[offset : offset + limit]

    def count(self) -> int:
        return int(self._collection.count())

    def ping(self) -> bool:
        self._client.heartbeat()
        return True
