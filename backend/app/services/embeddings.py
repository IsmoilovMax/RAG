"""Sentence-Transformers embedding service (CPU only, lazily loaded singleton)."""

from __future__ import annotations

import logging
import threading
import time
from typing import Protocol

logger = logging.getLogger(__name__)


class Embedder(Protocol):
    model_name: str

    @property
    def dimension(self) -> int: ...

    @property
    def is_loaded(self) -> bool: ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class SentenceTransformerEmbedder:
    """Wraps a SentenceTransformer model.

    The model is loaded exactly once (thread-safe) on first use and always on CPU.
    Embeddings are L2-normalised so cosine similarity == dot product.
    """

    def __init__(
        self,
        model_name: str,
        *,
        batch_size: int = 32,
        query_instruction: str = "",
        num_threads: int | None = None,
        cache_dir: str | None = None,
    ) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self.query_instruction = query_instruction
        self.num_threads = num_threads
        self.cache_dir = cache_dir
        self._model = None
        self._lock = threading.Lock()
        self._encode_lock = threading.Lock()

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def _load(self):
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is None:
                import torch
                from sentence_transformers import SentenceTransformer

                if self.num_threads:
                    torch.set_num_threads(self.num_threads)
                started = time.perf_counter()
                self._model = SentenceTransformer(
                    self.model_name, device="cpu", cache_folder=self.cache_dir
                )
                self._model.eval()
                logger.info(
                    "Embedding model loaded",
                    extra={
                        "model": self.model_name,
                        "dim": self._dimension_of(self._model),
                        "load_s": round(time.perf_counter() - started, 2),
                    },
                )
        return self._model

    def warmup(self) -> None:
        self._load()

    @staticmethod
    def _dimension_of(model) -> int:
        getter = getattr(model, "get_embedding_dimension", None) or model.get_sentence_embedding_dimension
        return int(getter())

    @property
    def dimension(self) -> int:
        return self._dimension_of(self._load())

    def _encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._load()
        # Serialise encode calls: torch already parallelises across CPU cores, and
        # concurrent encodes would only multiply peak memory.
        with self._encode_lock:
            vectors = model.encode(
                texts,
                batch_size=self.batch_size,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        return vectors.astype("float32").tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._encode(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._encode([f"{self.query_instruction}{text}"])[0]
