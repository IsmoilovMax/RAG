from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.db.models import DocumentStatus
from app.schemas.common import UTCDateTime


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    file_type: str
    mime_type: str | None
    size_bytes: int
    sha256: str
    status: DocumentStatus
    error_message: str | None
    progress: int
    page_count: int | None
    char_count: int | None
    chunk_count: int
    chunk_size: int | None
    chunk_overlap: int | None
    embedding_model: str | None
    processing_ms: int | None
    created_at: UTCDateTime
    updated_at: UTCDateTime
    processed_at: UTCDateTime | None


class DocumentList(BaseModel):
    items: list[DocumentOut]
    total: int


class UploadResult(BaseModel):
    filename: str
    status: Literal["accepted", "duplicate", "rejected"]
    document: DocumentOut | None = None
    error: str | None = None


class UploadResponse(BaseModel):
    results: list[UploadResult]
    accepted: int
    duplicates: int
    rejected: int


class ChunkOut(BaseModel):
    id: str
    text: str
    metadata: dict[str, Any]


class ChunkList(BaseModel):
    items: list[ChunkOut]
    document_id: str
    total: int


class ReindexResponse(BaseModel):
    queued: int
