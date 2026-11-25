from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import UTCDateTime


class SourceOut(BaseModel):
    index: int
    document_id: str
    filename: str
    file_type: str | None = None
    page: int | None = None
    section: str | None = None
    chunk_index: int | None = None
    similarity: float
    snippet: str
    cited: bool = False
    inferred: bool = False  # attribution derived from word overlap (no [n] in the answer)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    conversation_id: str
    role: str
    content: str
    sources: list[SourceOut] = []
    meta: dict[str, Any] = {}
    created_at: UTCDateTime


class ConversationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    created_at: UTCDateTime
    updated_at: UTCDateTime
    message_count: int = 0


class ConversationDetail(ConversationSummary):
    messages: list[MessageOut] = []


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=255)


class ConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None
    document_ids: list[str] | None = Field(default=None, max_length=100)

    @field_validator("question")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question must not be empty")
        return value


class ChatResponse(BaseModel):
    conversation_id: str
    user_message: MessageOut
    assistant_message: MessageOut
