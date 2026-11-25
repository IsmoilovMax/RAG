from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RuntimeSettings(BaseModel):
    """Settings that can be changed at runtime from the UI (persisted in the DB)."""

    model_config = ConfigDict(extra="forbid")

    llm_model: str = Field(min_length=1, max_length=200)
    llm_temperature: float = Field(ge=0.0, le=2.0)
    chunk_size: int = Field(ge=100, le=8000)
    chunk_overlap: int = Field(ge=0, le=2000)
    retrieval_top_k: int = Field(ge=1, le=20)
    similarity_threshold: float = Field(ge=0.0, le=1.0)
    relative_score_cutoff: float = Field(ge=0.0, le=1.0)
    max_context_chars: int = Field(ge=500, le=50000)
    history_turns: int = Field(ge=0, le=20)

    @model_validator(mode="after")
    def _overlap_lt_size(self) -> RuntimeSettings:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return self


class RuntimeSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm_model: str | None = Field(default=None, min_length=1, max_length=200)
    llm_temperature: float | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    retrieval_top_k: int | None = None
    similarity_threshold: float | None = None
    relative_score_cutoff: float | None = None
    max_context_chars: int | None = None
    history_turns: int | None = None


class SystemInfo(BaseModel):
    app_name: str
    environment: str
    embedding_model: str
    embedding_batch_size: int
    ollama_base_url: str
    ollama_num_ctx: int
    max_upload_mb: int
    max_files_per_upload: int
    supported_types: list[str]
    auth_enabled: bool
    database_backend: str


class SettingsResponse(BaseModel):
    settings: RuntimeSettings
    defaults: RuntimeSettings
    system: SystemInfo
    stale_documents: int = 0


class OllamaModel(BaseModel):
    name: str
    size_bytes: int | None = None
    parameter_size: str | None = None
    quantization: str | None = None
    family: str | None = None
    modified_at: str | None = None


class ModelsResponse(BaseModel):
    available: bool
    models: list[OllamaModel] = []
    current: str
    error: str | None = None


def model_dump_public(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")
