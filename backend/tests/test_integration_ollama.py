"""End-to-end answer generation against a real Ollama server (skipped if unavailable).

Run with:  pytest -m integration
"""

from __future__ import annotations

import asyncio
import os

import httpx
import pytest

from app.container import build_container
from app.services.prompts import NO_ANSWER
from app.services.rag import AnswerType
from scripts.generate_samples import generate
from tests.conftest import add_document, make_settings

pytestmark = [pytest.mark.integration, pytest.mark.model]

OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")


def _ollama_ready() -> bool:
    try:
        tags = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=3).json()
    except Exception:
        return False
    return any(m.get("name") in (MODEL, f"{MODEL}:latest") for m in tags.get("models", []))


@pytest.fixture(scope="module")
def live(tmp_path_factory):
    if not _ollama_ready():
        pytest.skip(f"Ollama with model {MODEL} not reachable at {OLLAMA_URL}")
    tmp = tmp_path_factory.mktemp("live")
    settings = make_settings(tmp, ollama_base_url=OLLAMA_URL, ollama_model=MODEL,
                             similarity_threshold=0.55, relative_score_cutoff=0.12)
    container = build_container(settings)
    for path in generate(tmp / "samples").values():
        add_document(container, path)
    yield container
    container.ingestion.shutdown()


def _ask(container, question):
    with container.db.session() as s:
        runtime = container.settings_service.get(s)
    return asyncio.run(container.rag.answer(question, [], runtime))


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("How many days of paid annual leave do employees get?", "28"),
        ("What is the payload of the Atlas X2 Pro?", "600"),
        ("Who is the sales lead for Iberia?", "Lucia Moreno"),
    ],
)
def test_live_grounded_answers(live, question, expected):
    answer, sources, answer_type, _ = _ask(live, question)
    assert answer_type == AnswerType.GROUNDED, answer
    assert expected.lower() in answer.lower(), answer
    assert sources


def test_live_follow_up_question(live):
    from app.services.rag import HistoryTurn

    history = [
        HistoryTurn("user", "How many days of annual leave do employees get?"),
        HistoryTurn("assistant", "Every full-time employee receives 28 days of paid annual leave per calendar year [1]."),
    ]
    with live.db.session() as s:
        runtime = live.settings_service.get(s)
    answer, _, answer_type, _ = asyncio.run(live.rag.answer("And how long is parental leave?", history, runtime))
    assert answer_type == AnswerType.GROUNDED, answer
    assert "18" in answer, answer


def test_live_unanswerable_question(live):
    answer, sources, answer_type, _ = _ask(live, "What is the capital of Australia?")
    assert answer_type == AnswerType.NO_CONTEXT
    assert answer == NO_ANSWER and sources == []
