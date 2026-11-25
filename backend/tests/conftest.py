"""Shared fixtures: isolated settings/storage, fake embedder and fake LLM."""

from __future__ import annotations

import hashlib
import math
import re
import shutil
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.container import Container, build_container  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.core.exceptions import LLMUnavailableError  # noqa: E402
from app.db.models import Document  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services.llm import ChatMessage, GenerationOptions  # noqa: E402
from app.services.vector_store import ChromaVectorStore  # noqa: E402
from scripts.generate_samples import generate  # noqa: E402

_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = set(
    "a an and are as at be by can do does for from how i in is it many much of on or the this to was "
    "what when where which who whom why will with won you your".split()
)


class HashEmbedder:
    """Deterministic bag-of-words embedder: fast, offline, lexically meaningful."""

    model_name = "test-hash-embedder"

    def __init__(self, dim: int = 512) -> None:
        self._dim = dim
        self.calls = 0

    @property
    def dimension(self) -> int:
        return self._dim

    @property
    def is_loaded(self) -> bool:
        return True

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        for token in _TOKEN.findall(text.lower()):
            if token in _STOPWORDS:
                continue
            idx = int(hashlib.md5(token.encode()).hexdigest(), 16) % self._dim
            vec[idx] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class FakeLLM:
    """Streams a scripted answer and records the prompts it received."""

    def __init__(self) -> None:
        self.response = "According to the documents, employees receive 28 days of annual leave [1]."
        self.fail_with: str | None = None
        self.calls: list[list[ChatMessage]] = []
        self.models = [{"name": "qwen2.5:3b", "size_bytes": 1_900_000_000, "parameter_size": "3.1B",
                        "quantization": "Q4_K_M", "family": "qwen2", "modified_at": None}]

    async def stream_chat(self, messages: list[ChatMessage], options: GenerationOptions) -> AsyncIterator[str]:
        self.calls.append(messages)
        if self.fail_with:
            raise LLMUnavailableError(self.fail_with)
        for word in re.findall(r"\S+\s*", self.response):
            yield word

    async def list_models(self) -> list[dict]:
        if self.fail_with:
            raise LLMUnavailableError(self.fail_with)
        return self.models

    async def health(self) -> dict:
        if self.fail_with:
            raise LLMUnavailableError(self.fail_with)
        return {"version": "test"}

    async def aclose(self) -> None:
        return None


def make_settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "data_dir": tmp_path / "data",
        "environment": "test",
        "log_level": "WARNING",
        "api_key": None,
        "database_url": None,
        "similarity_threshold": 0.2,  # tuned for the hash embedder
        "relative_score_cutoff": 0.5,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture(scope="session")
def sample_dir(tmp_path_factory) -> Path:
    directory = tmp_path_factory.mktemp("samples")
    generate(directory)
    return directory


@pytest.fixture
def settings(tmp_path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def container(settings, fake_llm) -> Iterator[Container]:
    c = build_container(
        settings,
        embedder=HashEmbedder(),
        llm=fake_llm,
        store=ChromaVectorStore(settings.chroma_dir, "test-docs"),
    )
    yield c
    c.ingestion.shutdown()
    c.db.dispose()


@pytest.fixture
def app_factory(tmp_path, fake_llm):
    """Build a TestClient with optional settings overrides."""
    clients: list[TestClient] = []

    def _make(**overrides) -> TestClient:
        s = make_settings(tmp_path / f"app{len(clients)}", **overrides)

        def factory(cfg: Settings) -> Container:
            return build_container(
                cfg,
                embedder=HashEmbedder(),
                llm=fake_llm,
                store=ChromaVectorStore(cfg.chroma_dir, "test-docs"),
            )

        client = TestClient(create_app(s, container_factory=factory, warmup=False))
        client.__enter__()
        clients.append(client)
        return client

    yield _make
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def client(app_factory) -> TestClient:
    return app_factory()


def add_document(container: Container, path: Path) -> str:
    """Register a file in the DB + upload dir and ingest it synchronously."""
    data = path.read_bytes()
    file_type = path.suffix.lstrip(".").lower()
    with container.db.session() as session:
        doc = Document(
            filename=path.name,
            stored_name="",
            file_type=file_type,
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )
        session.add(doc)
        session.flush()
        doc.stored_name = f"{doc.id}.{file_type}"
        doc_id = doc.id
    shutil.copy(path, container.settings.upload_dir / f"{doc_id}.{file_type}")
    container.ingestion.process(doc_id)
    return doc_id


def wait_for_ingestion(client: TestClient, timeout: float = 60.0) -> None:
    client.app.state.container.ingestion.wait_idle(timeout)
