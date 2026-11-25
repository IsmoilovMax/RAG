"""Prompt construction, grounding rules and answer generation (with a fake LLM)."""

from __future__ import annotations

import asyncio

import pytest

from app.schemas.settings import RuntimeSettings
from app.services.prompts import (
    ANSWER_INSTRUCTIONS,
    NO_ANSWER,
    SYSTEM_PROMPT,
    build_user_prompt,
    extract_citations,
    is_insufficient_answer,
    make_title,
    strip_citations,
)
from app.services.rag import AnswerType, HistoryTurn, finalize
from app.services.retrieval import RetrievedChunk
from tests.conftest import add_document


def _runtime(container, **overrides) -> RuntimeSettings:
    with container.db.session() as s:
        return container.settings_service.get(s).model_copy(update=overrides)


def _chunk(n: int, **kw) -> RetrievedChunk:
    base = {"id": f"c{n}", "text": f"Passage {n} text.", "similarity": 0.8, "document_id": "d", "filename": "f.pdf",
            "file_type": "pdf", "page": n}
    base.update(kw)
    return RetrievedChunk(**base)


def test_prompts_enforce_grounding():
    lowered = SYSTEM_PROMPT.lower()
    assert "only" in lowered and "never invent" in lowered
    assert NO_ANSWER in ANSWER_INSTRUCTIONS
    assert "Explanation:" in ANSWER_INSTRUCTIONS
    assert "[1]" in ANSWER_INSTRUCTIONS


def test_user_prompt_numbers_context_with_locations():
    prompt = build_user_prompt("What is X?", [_chunk(1), _chunk(2, filename="b.xlsx", file_type="xlsx", section="Sheet: S", page=1)])
    assert "[1] (f.pdf — page 1)\nPassage 1 text." in prompt
    assert "[2] (b.xlsx — Sheet: S)" in prompt
    assert prompt.endswith(ANSWER_INSTRUCTIONS)
    assert "Question: What is X?\n\nInstructions:" in prompt


def test_citation_helpers():
    assert extract_citations("A [1] B [3][2] C [9] [1]", max_index=3) == [1, 2, 3]
    assert strip_citations("Leave is 28 days [1][2]. Remote 3 days [3].") == "Leave is 28 days. Remote 3 days."


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (NO_ANSWER, True),
        (f'"{NO_ANSWER}"', True),
        ("The uploaded documents do not contain sufficient information to answer this question", True),
        ("Employees get 28 days [1].", False),
        ("Leave is 28 days [1]. " * 10 + NO_ANSWER, False),
    ],
)
def test_insufficient_detection(text, expected):
    assert is_insufficient_answer(text) is expected


def test_make_title():
    assert make_title("  short   question ") == "short question"
    assert len(make_title("x" * 200)) == 60


def test_no_context_skips_llm(container, fake_llm):
    answer, sources, answer_type, prepared = asyncio.run(
        container.rag.answer("What is the capital of Australia?", [], _runtime(container))
    )
    assert answer == NO_ANSWER
    assert sources == [] and answer_type == AnswerType.NO_CONTEXT
    assert fake_llm.calls == []  # the LLM is never called without context


def test_grounded_answer_with_citations(container, fake_llm, sample_dir):
    add_document(container, sample_dir / "employee_handbook.pdf")
    answer, sources, answer_type, prepared = asyncio.run(
        container.rag.answer("How many days of annual leave do employees get?", [], _runtime(container))
    )
    assert answer_type == AnswerType.GROUNDED
    assert "[1]" in answer
    assert sources and sources[0]["cited"] is True
    assert sources[0]["filename"] == "employee_handbook.pdf"
    assert sources[0]["page"] == 2
    assert "28 days" in sources[0]["snippet"]

    messages = fake_llm.calls[0]
    assert messages[0].role == "system" and messages[0].content == SYSTEM_PROMPT
    assert messages[-1].role == "user" and "[1] (employee_handbook.pdf" in messages[-1].content


def test_insufficient_answer_type(container, fake_llm, sample_dir):
    add_document(container, sample_dir / "employee_handbook.pdf")
    fake_llm.response = NO_ANSWER
    _, sources, answer_type, _ = asyncio.run(
        container.rag.answer("How many days of annual leave for interns?", [], _runtime(container))
    )
    assert answer_type == AnswerType.INSUFFICIENT
    assert sources and not any(s["cited"] for s in sources)


def test_history_is_included_without_stale_citations(container, fake_llm, sample_dir):
    add_document(container, sample_dir / "employee_handbook.pdf")
    history = [HistoryTurn("user", "How many leave days?"), HistoryTurn("assistant", "28 days [1].")]
    asyncio.run(container.rag.answer("And how many can be carried over?", history, _runtime(container, history_turns=2)))
    messages = fake_llm.calls[0]
    # Earlier questions are folded into the single user prompt; earlier answers are not.
    assert [m.role for m in messages] == ["system", "user"]
    prompt = messages[1].content
    assert "Previous question (for reference only): How many leave days?" in prompt
    assert "Assistant:" not in prompt
    assert prompt.index("Context passages") < prompt.index("Previous question") < prompt.index("Question: And")


def test_history_disabled(container, fake_llm, sample_dir):
    add_document(container, sample_dir / "employee_handbook.pdf")
    history = [HistoryTurn("user", "leave days?"), HistoryTurn("assistant", "28 days [1].")]
    asyncio.run(container.rag.answer("annual leave days", history, _runtime(container, history_turns=0)))
    assert [m.role for m in fake_llm.calls[0]] == ["system", "user"]
    assert "Previous question" not in fake_llm.calls[0][1].content


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("And how long is parental leave?", True),
        ("What about the X2 Pro?", True),
        ("How much does it cost?", True),
        ("Why?", True),
        ("What is the capital of Australia?", False),
        ("How many days of annual leave do employees get?", False),
    ],
)
def test_follow_up_detection(question, expected):
    from app.services.prompts import looks_like_follow_up

    assert looks_like_follow_up(question) is expected


def _prepared(*chunks):
    from app.services.rag import PreparedAnswer
    from app.services.retrieval import RetrievalResult

    return PreparedAnswer(question="q", retrieval=RetrievalResult(chunks=list(chunks)))


def test_empty_model_output_becomes_refusal():
    text, sources, kind = finalize(_prepared(_chunk(1)), "[1]\n[1]")
    assert text == NO_ANSWER and kind == AnswerType.INSUFFICIENT
    assert not any(s["cited"] for s in sources)


def test_uncited_answer_gets_inferred_attribution_and_loses_appended_refusal():
    faq = _chunk(1, text="Firmware updates are released monthly on the first Tuesday of each month.")
    other = _chunk(2, text="The robot has a LiDAR range of 30 metres.")
    raw = (
        "Firmware updates are released on the first Tuesday of each month and installed automatically.\n"
        f"{NO_ANSWER}"
    )
    text, sources, kind = finalize(_prepared(faq, other), raw)
    assert kind == AnswerType.GROUNDED
    assert NO_ANSWER not in text
    assert [(s["cited"], s["inferred"]) for s in sources] == [(True, True), (False, False)]


def test_explicit_citations_are_not_marked_inferred():
    _, sources, _ = finalize(_prepared(_chunk(1)), "Passage one says so [1].")
    assert sources[0]["cited"] and not sources[0]["inferred"]


@pytest.mark.parametrize(
    ("message", "kind"),
    [
        ("Hello", "greeting"),
        ("hi there!", "greeting"),
        ("Salom", "greeting"),
        ("Thank you!", "thanks"),
        ("rahmat", "thanks"),
        ("What can you do?", "help"),
        ("bye", "bye"),
        ("Hello, how many leave days do employees get?", None),
        ("What is the payload of the Atlas X2?", None),
    ],
)
def test_small_talk_detection(message, kind):
    from app.services.prompts import small_talk_kind

    assert small_talk_kind(message) == kind


def test_greeting_gets_friendly_reply_without_search_or_llm(container, fake_llm, sample_dir):
    add_document(container, sample_dir / "employee_handbook.pdf")
    answer, sources, answer_type, _ = asyncio.run(container.rag.answer("Hello!", [], _runtime(container)))
    assert answer_type == AnswerType.SMALL_TALK
    assert answer.startswith("Hello! I'm DocuMind")
    assert sources == [] and fake_llm.calls == []


def test_vague_question_scoped_to_a_document_is_still_answered(container, fake_llm, sample_dir):
    doc_id = add_document(container, sample_dir / "employee_handbook.pdf")
    runtime = _runtime(container, similarity_threshold=0.95)  # nothing passes normally
    _, _, unscoped_type, _ = asyncio.run(container.rag.answer("paid annual leave days carried over before March", [], runtime))
    assert unscoped_type == AnswerType.NO_CONTEXT

    _, sources, scoped_type, prepared = asyncio.run(
        container.rag.answer("paid annual leave days carried over before March", [], runtime, document_ids=[doc_id])
    )
    assert scoped_type == AnswerType.GROUNDED
    assert prepared.retrieval.relaxed is True
    assert sources and all(s["document_id"] == doc_id for s in sources)


def test_refusal_citations_are_removed():
    from app.services.prompts import tidy_answer

    assert tidy_answer(f"{NO_ANSWER} [1]", max_index=1) == NO_ANSWER


def test_finalize_marks_cited_sources():
    from app.services.rag import PreparedAnswer
    from app.services.retrieval import RetrievalResult

    prepared = PreparedAnswer(question="q", retrieval=RetrievalResult(chunks=[_chunk(1), _chunk(2)]))
    text, sources, kind = finalize(prepared, "Fact [2].")
    assert text == "Fact [2]."
    assert kind == AnswerType.GROUNDED
    assert [s["cited"] for s in sources] == [False, True]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # redundant refusal appended to a supported answer is removed
        (f"Leave is 28 days [1].\n\n{NO_ANSWER} [1]", "Leave is 28 days [1]."),
        # a leading citation is moved to the end of the line and duplicates collapse
        ("[1] Leave is 28 days. Carry-over is 5 days [1].", "Leave is 28 days. Carry-over is 5 days [1]."),
        # a citation after the full stop is moved before it
        ("The stipend is 600 euros. [1]", "The stipend is 600 euros [1]."),
        # verbatim repeated lines are dropped
        ("[1] A is B.\n[1] A is B.", "A is B [1]."),
        # list items keep their bullet
        ("- [2] Item one\n- Item two [3]", "- Item one [2]\n- Item two [3]"),
        # a genuine refusal is left untouched
        (NO_ANSWER, NO_ANSWER),
        # no citations: the refusal is the real answer, keep text as-is
        (f"Some words. {NO_ANSWER}", f"Some words. {NO_ANSWER}"),
    ],
)
def test_tidy_answer(raw, expected):
    from app.services.prompts import tidy_answer

    assert tidy_answer(raw) == expected


def test_tidy_answer_drops_invalid_and_orphan_citations():
    from app.services.prompts import tidy_answer

    assert tidy_answer("Lucia Moreno is the lead [1].\n[1]", max_index=2) == "Lucia Moreno is the lead [1]."
    assert tidy_answer("Updates ship monthly [3].", max_index=1) == "Updates ship monthly."
    assert tidy_answer("A [1] and B [2].", max_index=2) == "A [1] and B [2]."
