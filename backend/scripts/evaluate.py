"""Evaluate answer accuracy of a running DocuMind instance on the sample set.

Upload the files in samples/ first, then run:

    python scripts/evaluate.py [--url http://localhost:8000/api] [--api-key KEY]

For every example question it checks that the expected fact appears in the
answer and that the expected document is cited; unanswerable questions must be
refused. Exit code is non-zero when anything fails.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.generate_samples import EXAMPLE_QUESTIONS, UNANSWERABLE_QUESTIONS  # noqa: E402


def _norm(text: str) -> str:
    return text.lower().replace(",", "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://localhost:8000/api")
    parser.add_argument("--api-key", default=None)
    args = parser.parse_args()

    headers = {"X-API-Key": args.api_key} if args.api_key else {}
    client = httpx.Client(base_url=args.url, timeout=600, headers=headers)

    passed = 0
    total = len(EXAMPLE_QUESTIONS) + len(UNANSWERABLE_QUESTIONS)
    latencies: list[int] = []

    for question, source, fact in EXAMPLE_QUESTIONS:
        msg = client.post("/chat/ask", json={"question": question}).json()["assistant_message"]
        cited = {s["filename"] for s in msg["sources"] if s["cited"]}
        ok = _norm(fact) in _norm(msg["content"]) and source in cited
        passed += ok
        latencies.append(msg["meta"].get("latency_ms", 0))
        print(f"{'PASS' if ok else 'FAIL'}  {question}")
        print(f"      -> {msg['content'][:200]!r}  (cited: {sorted(cited) or '-'})")

    for question in UNANSWERABLE_QUESTIONS:
        msg = client.post("/chat/ask", json={"question": question}).json()["assistant_message"]
        ok = msg["meta"].get("answer_type") in ("no_context", "insufficient")
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'}  {question}  -> {msg['meta'].get('answer_type')}")

    avg = sum(latencies) / len(latencies) / 1000 if latencies else 0
    print(f"\n{passed}/{total} passed · average answer latency {avg:.1f}s")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
