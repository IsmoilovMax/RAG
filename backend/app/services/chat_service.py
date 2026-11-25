"""Conversation persistence and the streaming question-answering flow."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, func, select

from app.core.exceptions import AppError, NotFoundError
from app.db.models import Conversation, Message, utcnow
from app.db.session import Database
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConversationDetail,
    ConversationSummary,
    MessageOut,
)
from app.schemas.settings import RuntimeSettings
from app.services.prompts import make_title
from app.services.rag import AnswerType, HistoryTurn, PreparedAnswer, RagService, finalize, source_payload
from app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

DEFAULT_TITLE = "New conversation"
_HISTORY_EXCLUDED = {AnswerType.NO_CONTEXT, AnswerType.SMALL_TALK, "error"}


def sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@dataclass(slots=True)
class _Turn:
    conversation_id: str
    user_message: MessageOut
    history: list[HistoryTurn]
    runtime: RuntimeSettings


class ChatService:
    def __init__(self, *, db: Database, rag: RagService, settings_service: SettingsService) -> None:
        self.db = db
        self.rag = rag
        self.settings_service = settings_service

    # ---------------------------------------------------------- conversations
    def list_conversations(self, limit: int = 100) -> list[ConversationSummary]:
        with self.db.session() as session:
            counts = (
                select(Message.conversation_id, func.count(Message.id).label("n"))
                .group_by(Message.conversation_id)
                .subquery()
            )
            rows = session.execute(
                select(Conversation, func.coalesce(counts.c.n, 0))
                .outerjoin(counts, counts.c.conversation_id == Conversation.id)
                .order_by(Conversation.updated_at.desc())
                .limit(limit)
            ).all()
            return [
                ConversationSummary.model_validate(conv).model_copy(update={"message_count": int(n)})
                for conv, n in rows
            ]

    def get_conversation(self, conversation_id: str) -> ConversationDetail:
        with self.db.session() as session:
            conv = session.get(Conversation, conversation_id)
            if conv is None:
                raise NotFoundError("Conversation not found")
            messages = [MessageOut.model_validate(m) for m in conv.messages]
            return ConversationDetail(
                id=conv.id,
                title=conv.title,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                message_count=len(messages),
                messages=messages,
            )

    def create_conversation(self, title: str | None = None) -> ConversationSummary:
        with self.db.session() as session:
            conv = Conversation(title=(title or DEFAULT_TITLE).strip() or DEFAULT_TITLE)
            session.add(conv)
            session.flush()
            return ConversationSummary.model_validate(conv)

    def rename_conversation(self, conversation_id: str, title: str) -> ConversationSummary:
        with self.db.session() as session:
            conv = session.get(Conversation, conversation_id)
            if conv is None:
                raise NotFoundError("Conversation not found")
            conv.title = title.strip()
            session.flush()
            return ConversationSummary.model_validate(conv)

    def delete_conversation(self, conversation_id: str) -> None:
        with self.db.session() as session:
            conv = session.get(Conversation, conversation_id)
            if conv is None:
                raise NotFoundError("Conversation not found")
            session.delete(conv)

    def clear_messages(self, conversation_id: str) -> None:
        with self.db.session() as session:
            conv = session.get(Conversation, conversation_id)
            if conv is None:
                raise NotFoundError("Conversation not found")
            session.execute(delete(Message).where(Message.conversation_id == conversation_id))
            conv.title = DEFAULT_TITLE
            conv.updated_at = utcnow()

    # ------------------------------------------------------------ Q&A flow
    def _begin_turn(self, request: ChatRequest) -> _Turn:
        with self.db.session() as session:
            runtime = self.settings_service.get(session)
            if request.conversation_id:
                conv = session.get(Conversation, request.conversation_id)
                if conv is None:
                    raise NotFoundError("Conversation not found")
            else:
                conv = Conversation(title=DEFAULT_TITLE)
                session.add(conv)
                session.flush()

            history = self._history(conv.messages)
            if conv.title == DEFAULT_TITLE:
                conv.title = make_title(request.question)
            conv.updated_at = utcnow()
            user_msg = Message(
                conversation_id=conv.id,
                role="user",
                content=request.question,
                sources=[],
                meta={"document_ids": request.document_ids} if request.document_ids else {},
            )
            session.add(user_msg)
            session.flush()
            return _Turn(conv.id, MessageOut.model_validate(user_msg), history, runtime)

    @staticmethod
    def _history(messages: list[Message]) -> list[HistoryTurn]:
        """Successful Q/A pairs only: refusals and errors would bias the model."""
        turns: list[HistoryTurn] = []
        pending_user: Message | None = None
        for msg in messages:
            if msg.role == "user":
                pending_user = msg
            elif msg.role == "assistant" and pending_user is not None:
                if (msg.meta or {}).get("answer_type") not in _HISTORY_EXCLUDED:
                    turns.append(HistoryTurn("user", pending_user.content))
                    turns.append(HistoryTurn("assistant", msg.content))
                pending_user = None
        return turns

    def _save_assistant(
        self,
        conversation_id: str,
        content: str,
        sources: list[dict[str, Any]],
        meta: dict[str, Any],
    ) -> MessageOut:
        with self.db.session() as session:
            msg = Message(
                conversation_id=conversation_id,
                role="assistant",
                content=content,
                sources=sources,
                meta=meta,
            )
            session.add(msg)
            conv = session.get(Conversation, conversation_id)
            if conv is not None:
                conv.updated_at = utcnow()
            session.flush()
            return MessageOut.model_validate(msg)

    @staticmethod
    def _meta(prepared: PreparedAnswer, runtime: RuntimeSettings, answer_type: str, started: float) -> dict[str, Any]:
        return {
            "answer_type": answer_type,
            "model": runtime.llm_model if prepared.has_context else None,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "retrieval": prepared.retrieval.as_debug(),
            "similarity_threshold": runtime.similarity_threshold,
        }

    async def stream(self, request: ChatRequest) -> AsyncIterator[str]:
        started = time.perf_counter()
        try:
            turn = await asyncio.to_thread(self._begin_turn, request)
        except AppError as exc:
            yield sse("error", {"detail": exc.message})
            return

        yield sse("meta", {"conversation_id": turn.conversation_id, "user_message": turn.user_message.model_dump(mode="json")})

        tokens: list[str] = []
        saved = False
        prepared: PreparedAnswer | None = None
        try:
            prepared = await asyncio.to_thread(
                self.rag.prepare, request.question, turn.history, turn.runtime, request.document_ids
            )
            yield sse(
                "sources",
                {"sources": source_payload(prepared.retrieval.chunks), "retrieval": prepared.retrieval.as_debug()},
            )
            async for token in self.rag.stream(prepared, turn.runtime):
                tokens.append(token)
                yield sse("token", {"t": token})

            answer, sources, answer_type = finalize(prepared, "".join(tokens))
            message = self._save_assistant(
                turn.conversation_id, answer, sources, self._meta(prepared, turn.runtime, answer_type, started)
            )
            saved = True
            yield sse("done", {"message": message.model_dump(mode="json")})
        except AppError as exc:
            logger.warning("Answer generation failed", extra={"error": exc.message})
            message = self._save_assistant(
                turn.conversation_id,
                exc.message,
                [],
                {"answer_type": "error", "error": exc.message, "latency_ms": int((time.perf_counter() - started) * 1000)},
            )
            saved = True
            yield sse("error", {"detail": exc.message, "message": message.model_dump(mode="json")})
        except Exception:
            logger.exception("Unexpected streaming error")
            message = self._save_assistant(
                turn.conversation_id,
                "An unexpected error occurred while generating the answer.",
                [],
                {"answer_type": "error", "error": "internal_error"},
            )
            saved = True
            yield sse("error", {"detail": "An unexpected error occurred", "message": message.model_dump(mode="json")})
        finally:
            # Client disconnected mid-stream: keep the partial answer in history.
            if not saved and tokens and prepared is not None:
                answer, sources, answer_type = finalize(prepared, "".join(tokens))
                meta =self._meta(prepared, turn.runtime, answer_type, started) | {"interrupted": True}
                self._save_assistant(turn.conversation_id, answer, sources, meta)

    async def ask(self, request: ChatRequest) -> ChatResponse:
        started = time.perf_counter()
        turn = await asyncio.to_thread(self._begin_turn, request)
        answer, sources, answer_type, prepared = await self.rag.answer(
            request.question, turn.history, turn.runtime, request.document_ids
        )
        message = self._save_assistant(
            turn.conversation_id, answer, sources, self._meta(prepared, turn.runtime, answer_type, started)
        )
        return ChatResponse(
            conversation_id=turn.conversation_id,
            user_message=turn.user_message,
            assistant_message=message,
        )
