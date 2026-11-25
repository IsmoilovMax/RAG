"""Application configuration loaded from environment variables / .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_ROOT / ".env", BACKEND_ROOT.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application ---
    app_name: str = "DocuMind RAG"
    environment: Literal["development", "production", "test"] = "development"
    log_level: str = "INFO"
    log_json: bool = False
    api_prefix: str = "/api"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    # Optional shared secret. When set, every non-health endpoint requires it via
    # the "X-API-Key" header (or "Authorization: Bearer <key>").
    api_key: SecretStr | None = None

    # --- Storage ---
    data_dir: Path = BACKEND_ROOT / "data"
    database_url: str | None = None  # defaults to SQLite inside data_dir
    chroma_collection: str = "documents"

    # --- Uploads ---
    max_upload_mb: int = Field(default=50, ge=1, le=1024)
    max_files_per_upload: int = Field(default=20, ge=1, le=200)

    # --- Embeddings ---
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_batch_size: int = Field(default=32, ge=1, le=512)
    embedding_query_instruction: str = (
        "Represent this sentence for searching relevant passages: "
    )
    torch_num_threads: int | None = Field(default=None, ge=1)

    # --- Local LLM (Ollama) ---
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"
    ollama_timeout_s: float = Field(default=300.0, gt=0)
    ollama_num_ctx: int = Field(default=4096, ge=512)
    ollama_num_thread: int | None = Field(default=None, ge=1)
    ollama_keep_alive: str = "30m"

    # --- RAG defaults (overridable at runtime from the Settings page) ---
    llm_temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    chunk_size: int = Field(default=1000, ge=100, le=8000)
    chunk_overlap: int = Field(default=150, ge=0, le=2000)
    retrieval_top_k: int = Field(default=5, ge=1, le=20)
    similarity_threshold: float = Field(default=0.55, ge=0.0, le=1.0)
    relative_score_cutoff: float = Field(default=0.12, ge=0.0, le=1.0)
    max_context_chars: int = Field(default=6000, ge=500, le=50000)
    history_turns: int = Field(default=3, ge=0, le=20)

    # --- Background processing ---
    ingestion_workers: int = Field(default=1, ge=1, le=8)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip().startswith("["):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("api_key", mode="before")
    @classmethod
    def _empty_key_is_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def _check_chunking(self) -> Settings:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        return self

    # --- Derived paths ---
    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "chroma"

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'app.db').as_posix()}"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.chroma_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
