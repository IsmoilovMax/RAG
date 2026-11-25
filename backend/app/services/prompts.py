"""Prompt templates enforcing grounded, cited answers.

The prompts are tuned for small local models (e.g. qwen2.5:3b): a short system
prompt, with the concrete instructions placed right after the question, where
small models follow them most reliably. Avoid content-bearing examples in the
instructions - small models tend to copy them into unrelated answers.
"""

from __future__ import annotations

import re

from app.services.retrieval import RetrievedChunk

NO_ANSWER = (
    "The uploaded documents do not contain sufficient information to answer this question."
)

SYSTEM_PROMPT = (
    "You are DocuMind, a document assistant. You answer questions using only the context passages "
    "provided by the user, which are excerpts from their uploaded documents. Never use outside "
    "knowledge and never invent facts, numbers, names or dates."
)

ANSWER_INSTRUCTIONS = (
    "Instructions:\n"
    "- Answer the question in one or more complete sentences, using only the context passages above.\n"
    "- After each sentence, write the number of the passage it came from in square brackets, for example [1].\n"
    f"- If the passages do not contain the answer, reply only with: {NO_ANSWER}\n"
    "- If the passages answer only part of the question, answer that part and say which part is not covered.\n"
    '- If you add reasoning that is not written in the passages, put it in a final paragraph starting with "Explanation:".'
)

_CITATION = re.compile(r"\[(\d{1,2})\]")
_CITATION_GROUP = re.compile(r"\s*(\[\d{1,2}\])+")


def format_context(chunks: list[RetrievedChunk]) -> str:
    return "\n\n".join(
        f"[{number}] ({chunk.location()})\n{chunk.text.strip()}"
        for number, chunk in enumerate(chunks, start=1)
    )


def _one_line(text: str, max_chars: int = 300) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= max_chars else text[: max_chars - 1].rstrip() + "…"


def build_user_prompt(
    question: str,
    chunks: list[RetrievedChunk],
    previous_questions: list[str] | None = None,
    *,
    scoped: bool = False,
) -> str:
    """Single-turn prompt.

    For follow-ups only the user's earlier *questions* are included, as a
    reference for what "it"/"their"/"and the other one" refer to. Measured on
    qwen2.5:3b, replaying earlier *answers* (or multi-turn chat) made the model
    wrongly refuse follow-ups that the passages answer.
    """
    reference = ""
    if previous_questions:
        items = [_one_line(q) for q in previous_questions if q.strip()]
        if len(items) == 1:
            reference = f"Previous question (for reference only): {items[0]}\n\n"
        elif items:
            listed = "\n".join(f"- {q}" for q in items)
            reference = f"Previous questions (for reference only):\n{listed}\n\n"
    header = "Context passages:"
    if scoped:
        names = sorted({c.filename for c in chunks})
        header = (
            f"The user selected the document {', '.join(names)} and is asking about it. "
            "Excerpts from it, in reading order (the first lines are usually its title, or the "
            "name of the person or organisation it is about):"
        )
    return (
        f"{header}\n\n{format_context(chunks)}\n\n"
        f"{reference}"
        f"Question: {question.strip()}\n\n"
        f"{ANSWER_INSTRUCTIONS}"
    )


_FOLLOW_UP_START = re.compile(
    r"^(and|but|also|so|then|what about|how about|and what|and how|or)\b", re.IGNORECASE
)
_FOLLOW_UP_REF = re.compile(
    r"\b(it|its|they|them|their|this|that|these|those|he|she|his|her|there|same|previous|above|"
    r"former|latter|one|ones|else|more)\b",
    re.IGNORECASE,
)


def looks_like_follow_up(question: str) -> bool:
    """Heuristic: does the question depend on earlier turns to be understood?"""
    q = question.strip()
    words = q.split()
    return len(words) <= 3 or bool(_FOLLOW_UP_START.match(q)) or bool(_FOLLOW_UP_REF.search(q))


def extract_citations(answer: str, max_index: int) -> list[int]:
    found = {int(m) for m in _CITATION.findall(answer)}
    return sorted(n for n in found if 1 <= n <= max_index)


def strip_citations(text: str) -> str:
    """Remove [n] markers (used when replaying history, where numbers are stale)."""
    return _CITATION_GROUP.sub("", text).strip()


def is_insufficient_answer(answer: str) -> bool:
    normalized = re.sub(r"\s+", " ", answer.strip().strip('"').lower())
    marker = NO_ANSWER.lower().rstrip(".")
    if normalized.startswith(marker):
        return True
    if marker not in normalized:
        return False
    # The refusal appears mid-answer: it is the real answer only when the rest
    # is short and cites nothing.
    remainder = normalized.replace(marker, "")
    return not _CITATION.search(remainder) and len(remainder.strip(' ."')) < 80


_NO_ANSWER_SENTENCE = re.compile(
    r"[ \t]*\"?" + re.escape(NO_ANSWER.rstrip(".")) + r"\.?\"?([ \t]*\[\d{1,2}\])*", re.IGNORECASE
)
_LEADING_CITES = re.compile(r"^((?:\[\d{1,2}\]\s*)+)(?=\S)")
_REPEATED_CITE = re.compile(r"(\[\d{1,2}\])(?:\s*\1)+")
_CITE_AFTER_PUNCT = re.compile(r"([.!?])((?:[ \t]*\[\d{1,2}\])+)(?=\s|$)")
_LIST_PREFIX = re.compile(r"^(\s*(?:[-*•]|\d+[.)])\s+)")


def _tidy_line(line: str) -> str:
    prefix_match = _LIST_PREFIX.match(line)
    prefix = prefix_match.group(1) if prefix_match else ""
    body = line[len(prefix) :]
    lead = _LEADING_CITES.match(body)
    if lead:
        cites = "".join(lead.group(1).split())
        rest = body[lead.end() :].rstrip()
        # Move the leading citation to the end of the line (before final punctuation).
        if rest and rest[-1] in ".!?":
            body = f"{rest[:-1]} {cites}{rest[-1]}"
        else:
            body = f"{rest} {cites}"
    body = _CITE_AFTER_PUNCT.sub(lambda m: f" {''.join(m.group(2).split())}{m.group(1)}", body)
    body = _REPEATED_CITE.sub(r"\1", body)
    return prefix + body


def tidy_answer(answer: str, max_index: int | None = None) -> str:
    """Repair common small-model formatting slips without changing the content.

    * citations to passages that do not exist (> max_index) are removed;
    * a redundant "documents do not contain sufficient information" sentence
      appended to an answer that the passages do support is removed;
    * citations placed at the start of a line or after the full stop are moved
      to the end of the sentence, and repeated citations are collapsed;
    * lines repeated verbatim, or holding nothing but citations, are dropped.
    """
    text = answer.strip()
    if max_index is not None:
        text = _CITATION.sub(lambda m: m.group(0) if 1 <= int(m.group(1)) <= max_index else "", text)
        text = re.sub(r"[ \t]+([.!?,;:])", r"\1", text).strip()
    if not text:
        return text
    if is_insufficient_answer(text):
        # A refusal cites nothing.
        return strip_citations(text).strip('"').strip()
    stripped = _NO_ANSWER_SENTENCE.sub("", text).strip()
    # Drop the refusal when a substantive answer precedes it.
    if stripped and (_CITATION.search(stripped) or len(stripped) >= 80):
        text = stripped

    lines: list[str] = []
    seen: set[str] = set()
    for raw in text.split("\n"):
        line = _tidy_line(raw) if raw.strip() else ""
        if line and not _CITATION_GROUP.sub("", line).strip():
            continue  # a line holding only citation markers
        key = re.sub(r"\W+", "", line.lower())
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        lines.append(line)
    text = "\n".join(lines)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


_WORD = re.compile(r"[a-z0-9][a-z0-9\-']+")
_STOP = frozenset(
    "the and for are was were with that this from have has had not but can its into than then they them "
    "their there these those what when where which who whom will would should could about also each per "
    "all any our your you passage passages document documents context".split()
)


def _content_words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 2}


def infer_citations(answer: str, passages: list[str], min_overlap: float = 0.5) -> list[int]:
    """Attribute an answer that carries no [n] markers to the passage(s) it came from.

    Uses content-word overlap between the answer and each passage. Only used for
    provenance display (sources are flagged as *inferred*), never to alter text.
    """
    words = _content_words(answer)
    if len(words) < 3:
        return []
    scores = [len(words & _content_words(p)) / len(words) for p in passages]
    best = max(scores, default=0.0)
    if best < min_overlap:
        return []
    return [i + 1 for i, s in enumerate(scores) if s >= best - 0.1]


_GREETING = re.compile(
    r"^(hi|hello|hey|hiya|yo|good (morning|afternoon|evening|day)|greetings|salom|assalomu? ?alaykum|"
    r"привет|здравствуйте|салом)( there| everyone| all)?$"
)
_THANKS = re.compile(r"^(thanks?( you)?( (so|very) much)?|thx|ty|cheers|rahmat|katta rahmat|спасибо)$")
_BYE = re.compile(r"^(bye|goodbye|see you|xayr|пока|до свидания)$")
_HELP = re.compile(
    r"^(help|who are you|what are you|what can you do|how does this work|how do you work|"
    r"what do you do|sen kimsan|siz kimsiz|кто ты)$"
)

SMALL_TALK_REPLIES = {
    "greeting": (
        "Hello! I'm DocuMind. Ask me anything about your uploaded documents (a policy, a figure, "
        "a name or a date) and I'll answer using only what they say, with citations to the exact passages."
    ),
    "thanks": "You're welcome! Ask me anything else about your documents.",
    "bye": "Goodbye! Your conversation is saved in the history whenever you want to continue.",
    "help": (
        "I'm DocuMind, an assistant that answers questions **only from your uploaded documents**. "
        "I search them for the most relevant passages, answer from those passages, and cite them as [n]. "
        "If the documents don't cover a question, I'll say so instead of guessing.\n\n"
        "Try asking about a specific policy, number, name or date in your files."
    ),
}


def small_talk_kind(question: str) -> str | None:
    """Detect greetings / thanks / meta questions that need no document search."""
    q = re.sub(r"[\s!.?,;:)(]+", " ", question.lower()).strip()
    if not q or len(q.split()) > 6:
        return None
    for kind, pattern in (("greeting", _GREETING), ("thanks", _THANKS), ("bye", _BYE), ("help", _HELP)):
        if pattern.match(q):
            return kind
    return None


def make_title(question: str, limit: int = 60) -> str:
    title = re.sub(r"\s+", " ", question).strip()
    return title if len(title) <= limit else title[: limit - 1].rstrip() + "…"
