"""RAG orchestration: retrieve context, build prompt, generate a grounded answer."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.schemas.settings import RuntimeSettings
from app.services.llm import ChatMessage, GenerationOptions, LLMClient
from app.services.prompts import (
    NO_ANSWER,
    SMALL_TALK_REPLIES,
    SYSTEM_PROMPT,
    build_user_prompt,
    extract_citations,
    infer_citations,
    is_insufficient_answer,
    looks_like_follow_up,
    small_talk_kind,
    tidy_answer,
)
from app.services.retrieval import RetrievalResult, RetrievedChunk, Retriever

logger = logging.getLogger(__name__)

SNIPPET_CHARS = 1200
# Minimum similarity when the user scoped the question to specific documents.
SCOPED_SIMILARITY_FLOOR = 0.3


class AnswerType:
    GROUNDED = "grounded"  # answered from retrieved context
    INSUFFICIENT = "insufficient"  # context retrieved, but the LLM found it insufficient
    NO_CONTEXT = "no_context"  # nothing passed the similarity threshold: LLM not called
    SMALL_TALK = "small_talk"  # greeting/thanks/help: canned reply, no search, no LLM


@dataclass(slots=True)
class HistoryTurn:
    role: str
    content: str


@dataclass(slots=True)
class PreparedAnswer:
    question: str
    retrieval: RetrievalResult
    messages: list[ChatMessage] = field(default_factory=list)
    small_talk: str | None = None  # kind of small talk, when detected

    @property
    def has_context(self) -> bool:
        return bool(self.retrieval.chunks)


def source_payload(
    chunks: list[RetrievedChunk], cited: list[int] | None = None, *, inferred: bool = False
) -> list[dict[str, Any]]:
    """`cited` marks passages the answer relies on; `inferred` means the model gave no
    [n] markers and attribution was derived from word overlap instead."""
    cited_set = set(cited or [])
    return [
        {
            "index": number,
            "document_id": c.document_id,
            "filename": c.filename,
            "file_type": c.file_type,
            "page": c.page,
            "section": c.section,
            "chunk_index": c.chunk_index,
            "similarity": round(c.similarity, 4),
            "snippet": c.text[:SNIPPET_CHARS],
            "cited": number in cited_set,
            "inferred": inferred and number in cited_set,
        }
        for number, c in enumerate(chunks, start=1)
    ]


class RagService:
    def __init__(self, retriever: Retriever, llm: LLMClient, *, num_ctx: int, num_thread: int | None, keep_alive: str) -> None:
        self.retriever = retriever
        self.llm = llm
        self.num_ctx = num_ctx
        self.num_thread = num_thread
        self.keep_alive = keep_alive

    def prepare(
        self,
        question: str,
        history: list[HistoryTurn],
        runtime: RuntimeSettings,
        document_ids: list[str] | None = None,
    ) -> PreparedAnswer:
        """Retrieve context and build LLM messages (CPU-bound: call from a thread)."""
        kind = small_talk_kind(question)
        if kind is not None:
            return PreparedAnswer(question=question, retrieval=RetrievalResult(), small_talk=kind)

        turns = history[-(runtime.history_turns * 2) :] if runtime.history_turns else []
        # Follow-up questions ("and what about the X2 Pro?") rarely embed well on
        # their own, so they are also searched with the previous question prepended.
        # Self-contained questions are not, which keeps the threshold guard strict.
        previous_user = next((t.content for t in reversed(turns) if t.role == "user"), None)
        extra = (
            [f"{previous_user}\n{question}"]
            if previous_user and looks_like_follow_up(question)
            else []
        )
        retrieval = self.retriever.retrieve(
            question,
            top_k=runtime.retrieval_top_k,
            similarity_threshold=runtime.similarity_threshold,
            relative_cutoff=runtime.relative_score_cutoff,
            max_context_chars=runtime.max_context_chars,
            document_ids=document_ids,
            extra_queries=extra,
        )
        if not retrieval.chunks and document_ids:
            # The user explicitly chose the document(s) this question is about, so a
            # vague question ("what is the name?", "summarise this") should still be
            # answered from them. Use their best passages above a low sanity floor;
            # the grounding prompt still forbids anything not in those passages.
            retrieval = self.retriever.retrieve(
                question,
                top_k=runtime.retrieval_top_k,
                similarity_threshold=min(runtime.similarity_threshold, SCOPED_SIMILARITY_FLOOR),
                relative_cutoff=1.0,
                max_context_chars=runtime.max_context_chars,
                document_ids=document_ids,
                extra_queries=extra,
            )
            # Vague questions often concern the document's opening (title, name, topic),
            # which rarely ranks high by similarity: put it first.
            have = {c.id for c in retrieval.chunks}
            openings = [
                c for c in self.retriever.opening_chunks(question, document_ids[:3]) if c.id not in have
            ]
            chosen = (openings + retrieval.chunks)[: max(runtime.retrieval_top_k, len(openings))]
            # Present them in reading order so the document reads naturally.
            order = {doc_id: i for i, doc_id in enumerate(document_ids)}
            chosen.sort(key=lambda c: (order.get(c.document_id, 99), c.chunk_index or 0))
            retrieval.chunks = chosen
            retrieval.relaxed = bool(chosen)
        prepared = PreparedAnswer(question=question, retrieval=retrieval)
        if not retrieval.chunks:
            return prepared

        previous_questions = [t.content for t in turns if t.role == "user"]
        prepared.messages = [
            ChatMessage("system", SYSTEM_PROMPT),
            ChatMessage(
                "user",
                build_user_prompt(question, retrieval.chunks, previous_questions, scoped=retrieval.relaxed),
            ),
        ]
        return prepared

    def options(self, runtime: RuntimeSettings) -> GenerationOptions:
        return GenerationOptions(
            model=runtime.llm_model,
            temperature=runtime.llm_temperature,
            num_ctx=self.num_ctx,
            num_thread=self.num_thread,
            keep_alive=self.keep_alive,
        )

    async def stream(self, prepared: PreparedAnswer, runtime: RuntimeSettings) -> AsyncIterator[str]:
        if prepared.small_talk:
            yield SMALL_TALK_REPLIES[prepared.small_talk]
            return
        if not prepared.has_context:
            yield NO_ANSWER
            return
        async for token in self.llm.stream_chat(prepared.messages, self.options(runtime)):
            yield token

    async def answer(
        self,
        question: str,
        history: list[HistoryTurn],
        runtime: RuntimeSettings,
        document_ids: list[str] | None = None,
    ) -> tuple[str, list[dict[str, Any]], str, PreparedAnswer]:
        prepared = await asyncio.to_thread(self.prepare, question, history, runtime, document_ids)
        parts = [token async for token in self.stream(prepared, runtime)]
        text, sources, answer_type = finalize(prepared, "".join(parts))
        return text, sources, answer_type, prepared


def finalize(prepared: PreparedAnswer, answer: str) -> tuple[str, list[dict[str, Any]], str]:
    """Return the tidied answer text, source payload (with cited flags) and answer type."""
    chunks = prepared.retrieval.chunks
    if prepared.small_talk:
        return answer.strip(), [], AnswerType.SMALL_TALK
    if not chunks:
        return answer.strip(), [], AnswerType.NO_CONTEXT
    text = tidy_answer(answer, max_index=len(chunks)) or NO_ANSWER
    if is_insufficient_answer(text):
        return text, source_payload(chunks), AnswerType.INSUFFICIENT
    cited = extract_citations(text, len(chunks))
    inferred = False
    if not cited:
        cited = infer_citations(text, [c.text for c in chunks])
        inferred = bool(cited)
    return text, source_payload(chunks, cited, inferred=inferred), AnswerType.GROUNDED
