from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class ComponentHealth(BaseModel):
    status: Literal["ok", "degraded", "error"]
    detail: str | None = None
    info: dict[str, Any] = {}


class ReadinessResponse(BaseModel):
    status: Literal["ok", "degraded", "error"]
    components: dict[str, ComponentHealth]


class StatsResponse(BaseModel):
    documents_total: int
    documents_by_status: dict[str, int]
    documents_by_type: dict[str, int]
    total_chunks: int
    vector_count: int
    total_size_bytes: int
    conversations: int
    messages: int
    questions_answered: int
    answers_by_type: dict[str, int]
    avg_latency_ms: float | None
    processing_queue: int
    recent_documents: list[dict[str, Any]]
