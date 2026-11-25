from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse

from app.api.deps import get_container
from app.container import Container
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConversationCreate,
    ConversationDetail,
    ConversationSummary,
    ConversationUpdate,
)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/stream")
async def chat_stream(request: ChatRequest, container: Container = Depends(get_container)) -> StreamingResponse:
    """Answer a question with Server-Sent Events.

    Events: `meta` (conversation + user message), `sources` (retrieved passages),
    `token` (incremental answer text), `done` (saved assistant message) or `error`.
    """
    return StreamingResponse(
        container.chat.stream(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@router.post("/ask", response_model=ChatResponse)
async def chat_ask(request: ChatRequest, container: Container = Depends(get_container)) -> ChatResponse:
    """Non-streaming variant, convenient for scripts and integrations."""
    return await container.chat.ask(request)


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(
    limit: int = Query(default=100, ge=1, le=500), container: Container = Depends(get_container)
) -> list[ConversationSummary]:
    return container.chat.list_conversations(limit)


@router.post("/conversations", response_model=ConversationSummary, status_code=status.HTTP_201_CREATED)
def create_conversation(body: ConversationCreate, container: Container = Depends(get_container)) -> ConversationSummary:
    return container.chat.create_conversation(body.title)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: str, container: Container = Depends(get_container)) -> ConversationDetail:
    return container.chat.get_conversation(conversation_id)


@router.patch("/conversations/{conversation_id}", response_model=ConversationSummary)
def rename_conversation(
    conversation_id: str, body: ConversationUpdate, container: Container = Depends(get_container)
) -> ConversationSummary:
    return container.chat.rename_conversation(conversation_id, body.title)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: str, container: Container = Depends(get_container)) -> None:
    container.chat.delete_conversation(conversation_id)


@router.delete("/conversations/{conversation_id}/messages", status_code=status.HTTP_204_NO_CONTENT)
def clear_conversation(conversation_id: str, container: Container = Depends(get_container)) -> None:
    container.chat.clear_messages(conversation_id)
