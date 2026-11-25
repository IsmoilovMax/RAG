"""HTTP API endpoints."""

from __future__ import annotations

import json

import pytest

from app.services.prompts import NO_ANSWER
from tests.conftest import wait_for_ingestion


def upload(client, *paths):
    files = [("files", (p.name, p.read_bytes(), "application/octet-stream")) for p in paths]
    return client.post("/api/documents", files=files)


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        name, data = "message", ""
        for line in block.split("\n"):
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                data += line[6:]
        events.append((name, json.loads(data)))
    return events


@pytest.fixture
def ready_client(client, sample_dir):
    res = upload(client, sample_dir / "employee_handbook.pdf", sample_dir / "support_faq.txt")
    assert res.status_code == 200 and res.json()["accepted"] == 2
    wait_for_ingestion(client)
    return client


# ---------------------------------------------------------------- health
def test_health_endpoints(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    ready = client.get("/api/health/ready")
    assert ready.status_code == 200
    body = ready.json()
    assert body["status"] == "ok"
    assert set(body["components"]) == {"database", "vector_store", "embeddings", "llm"}


def test_readiness_degraded_when_llm_down(client, fake_llm):
    fake_llm.fail_with = "connection refused"
    body = client.get("/api/health/ready").json()
    assert body["status"] == "degraded"
    assert body["components"]["llm"]["status"] == "error"


def test_readiness_flags_missing_model(client, fake_llm):
    fake_llm.models = [{"name": "llama3.2:1b"}]
    llm = client.get("/api/health/ready").json()["components"]["llm"]
    assert llm["status"] == "degraded" and "ollama pull" in llm["detail"]


def test_security_headers(client):
    res = client.get("/api/health")
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-frame-options"] == "DENY"


# -------------------------------------------------------------- documents
def test_upload_multiple_and_process(client, sample_dir):
    paths = [sample_dir / n for n in ("employee_handbook.pdf", "atlas_x2_specification.docx", "q3_sales_report.xlsx",
                                      "onboarding_presentation.pptx", "support_faq.txt", "inventory.csv")]
    res = upload(client, *paths)
    assert res.status_code == 200
    body = res.json()
    assert body["accepted"] == 6 and body["duplicates"] == 0 and body["rejected"] == 0
    assert all(r["document"]["status"] in ("pending", "processing", "ready") for r in body["results"])

    wait_for_ingestion(client)
    listing = client.get("/api/documents").json()
    assert listing["total"] == 6
    assert {d["status"] for d in listing["items"]} == {"ready"}
    assert all(d["chunk_count"] > 0 for d in listing["items"])


def test_duplicate_upload_is_detected(client, sample_dir):
    path = sample_dir / "support_faq.txt"
    assert upload(client, path).json()["accepted"] == 1
    again = upload(client, path).json()
    assert again["duplicates"] == 1
    assert again["results"][0]["status"] == "duplicate"
    assert client.get("/api/documents").json()["total"] == 1


def test_upload_rejections(client, tmp_path):
    exe = tmp_path / "virus.exe"
    exe.write_bytes(b"MZ....")
    fake_pdf = tmp_path / "fake.pdf"
    fake_pdf.write_text("not a pdf")
    empty = tmp_path / "empty.txt"
    empty.write_bytes(b"")
    body = upload(client, exe, fake_pdf, empty).json()
    assert body["rejected"] == 3
    errors = [r["error"] for r in body["results"]]
    assert "Unsupported file type" in errors[0]
    assert "not a valid PDF" in errors[1]
    assert "empty" in errors[2].lower()
    assert client.get("/api/documents").json()["total"] == 0
    # No temp files are left behind.
    container = client.app.state.container
    assert list(container.settings.upload_dir.glob("*.part")) == []


def test_upload_size_limit(app_factory, tmp_path):
    client = app_factory(max_upload_mb=1)
    big = tmp_path / "big.txt"
    big.write_bytes(b"a" * (1024 * 1024 + 10))
    body = upload(client, big).json()
    assert body["rejected"] == 1 and "1 MB" in body["results"][0]["error"]


def test_too_many_files(app_factory, tmp_path):
    client = app_factory(max_files_per_upload=2)
    paths = []
    for i in range(3):
        p = tmp_path / f"f{i}.txt"
        p.write_text(f"file {i}")
        paths.append(p)
    res = upload(client, *paths)
    assert res.status_code == 422 and "at most 2" in res.json()["detail"]


def test_filename_is_sanitised(client):
    res = client.post("/api/documents", files=[("files", ("../../etc/pass<wd>.txt", b"hello there", "text/plain"))])
    doc = res.json()["results"][0]["document"]
    assert doc["filename"] == "pass_wd_.txt"


def test_document_detail_chunks_download(ready_client):
    doc = next(d for d in ready_client.get("/api/documents").json()["items"] if d["file_type"] == "pdf")
    detail = ready_client.get(f"/api/documents/{doc['id']}").json()
    assert detail["page_count"] == 3 and detail["status"] == "ready"

    chunks = ready_client.get(f"/api/documents/{doc['id']}/chunks").json()
    assert chunks["total"] == doc["chunk_count"] and chunks["items"]
    assert chunks["items"][0]["metadata"]["page"] == 1

    file = ready_client.get(f"/api/documents/{doc['id']}/file")
    assert file.status_code == 200 and file.content.startswith(b"%PDF")


def test_list_filters(ready_client):
    assert ready_client.get("/api/documents", params={"q": "handbook"}).json()["total"] == 1
    assert ready_client.get("/api/documents", params={"q": "txt"}).json()["total"] == 1
    assert ready_client.get("/api/documents", params={"status": "failed"}).json()["total"] == 0
    assert ready_client.get("/api/documents", params={"status": "bogus"}).status_code == 422


def test_delete_document_removes_vectors_and_file(ready_client):
    container = ready_client.app.state.container
    doc = ready_client.get("/api/documents").json()["items"][0]
    before = container.store.count()
    assert ready_client.delete(f"/api/documents/{doc['id']}").status_code == 204
    assert container.store.count() == before - doc["chunk_count"]
    assert ready_client.get(f"/api/documents/{doc['id']}").status_code == 404
    assert not list(container.settings.upload_dir.glob(f"{doc['id']}.*"))
    assert ready_client.delete(f"/api/documents/{doc['id']}").status_code == 404


def test_reprocess_and_reindex(ready_client):
    doc = ready_client.get("/api/documents").json()["items"][0]
    res = ready_client.post(f"/api/documents/{doc['id']}/reprocess")
    assert res.status_code == 200
    wait_for_ingestion(ready_client)
    assert ready_client.post("/api/documents/reindex").json()["queued"] == 2
    wait_for_ingestion(ready_client)
    assert {d["status"] for d in ready_client.get("/api/documents").json()["items"]} == {"ready"}


def test_unknown_document_404(client):
    assert client.get("/api/documents/nope").status_code == 404
    assert client.get("/api/documents/nope/chunks").status_code == 404


# ------------------------------------------------------------------- chat
def test_chat_stream_grounded(ready_client, fake_llm):
    res = ready_client.post("/api/chat/stream", json={"question": "How many days of annual leave do employees get?"})
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(res.text)
    names = [e[0] for e in events]
    assert names[0] == "meta" and names[1] == "sources" and names[-1] == "done"
    assert "token" in names

    sources = events[1][1]["sources"]
    assert sources and sources[0]["filename"] == "employee_handbook.pdf" and sources[0]["page"] == 2
    tokens = "".join(e[1]["t"] for e in events if e[0] == "token")
    done = events[-1][1]["message"]
    assert done["content"] == tokens.strip()
    assert done["meta"]["answer_type"] == "grounded"
    assert done["sources"][0]["cited"] is True

    conv_id = events[0][1]["conversation_id"]
    conv = ready_client.get(f"/api/chat/conversations/{conv_id}").json()
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]
    assert conv["title"].startswith("How many days")


def test_chat_stream_no_context(ready_client, fake_llm):
    events = parse_sse(ready_client.post("/api/chat/stream", json={"question": "Who won the 1998 FIFA World Cup?"}).text)
    done = events[-1][1]["message"]
    assert done["content"] == NO_ANSWER
    assert done["meta"]["answer_type"] == "no_context"
    assert events[1][1]["sources"] == []
    assert fake_llm.calls == []


def test_chat_stream_llm_error(ready_client, fake_llm):
    fake_llm.fail_with = "Cannot reach Ollama"
    events = parse_sse(ready_client.post("/api/chat/stream", json={"question": "annual leave days"}).text)
    assert events[-1][0] == "error"
    assert events[-1][1]["detail"] == "Cannot reach Ollama"
    assert events[-1][1]["message"]["meta"]["answer_type"] == "error"


def test_chat_follow_up_uses_history(ready_client, fake_llm):
    first = parse_sse(ready_client.post("/api/chat/stream", json={"question": "How many days of annual leave?"}).text)
    conv_id = first[0][1]["conversation_id"]
    ready_client.post("/api/chat/stream", json={"question": "And how many can be carried over?", "conversation_id": conv_id})
    prompt = fake_llm.calls[1][-1].content
    assert "Previous question (for reference only): How many days of annual leave?" in prompt
    conv = ready_client.get(f"/api/chat/conversations/{conv_id}").json()
    assert conv["message_count"] == 4


def test_chat_document_scope(ready_client, fake_llm):
    docs = ready_client.get("/api/documents").json()["items"]
    faq = next(d for d in docs if d["file_type"] == "txt")
    body = ready_client.post(
        "/api/chat/ask", json={"question": "annual leave days warranty", "document_ids": [faq["id"]]}
    ).json()
    assert {s["document_id"] for s in body["assistant_message"]["sources"]} <= {faq["id"]}


def test_chat_ask_non_streaming(ready_client):
    res = ready_client.post("/api/chat/ask", json={"question": "How many days of annual leave do employees get?"})
    assert res.status_code == 200
    body = res.json()
    assert body["assistant_message"]["meta"]["answer_type"] == "grounded"
    assert body["user_message"]["content"].startswith("How many")


def test_chat_validation(client):
    assert client.post("/api/chat/ask", json={"question": "   "}).status_code == 422
    assert client.post("/api/chat/ask", json={"question": "x" * 5000}).status_code == 422
    events = parse_sse(client.post("/api/chat/stream", json={"question": "hi", "conversation_id": "missing"}).text)
    assert events == [("error", {"detail": "Conversation not found"})]


def test_conversation_crud_and_clear(ready_client):
    conv = ready_client.post("/api/chat/conversations", json={}).json()
    assert conv["title"] == "New conversation"
    ready_client.post("/api/chat/ask", json={"question": "annual leave", "conversation_id": conv["id"]})
    listed = ready_client.get("/api/chat/conversations").json()
    assert listed[0]["id"] == conv["id"] and listed[0]["message_count"] == 2

    renamed = ready_client.patch(f"/api/chat/conversations/{conv['id']}", json={"title": "Leave"}).json()
    assert renamed["title"] == "Leave"

    assert ready_client.delete(f"/api/chat/conversations/{conv['id']}/messages").status_code == 204
    assert ready_client.get(f"/api/chat/conversations/{conv['id']}").json()["messages"] == []

    assert ready_client.delete(f"/api/chat/conversations/{conv['id']}").status_code == 204
    assert ready_client.get(f"/api/chat/conversations/{conv['id']}").status_code == 404


# --------------------------------------------------------------- settings
def test_settings_roundtrip(client):
    body = client.get("/api/settings").json()
    assert body["settings"]["llm_model"] == "qwen2.5:3b"
    assert body["system"]["embedding_model"] == "BAAI/bge-small-en-v1.5"
    assert "pdf" in body["system"]["supported_types"]

    updated = client.put("/api/settings", json={"retrieval_top_k": 8, "similarity_threshold": 0.6}).json()
    assert updated["settings"]["retrieval_top_k"] == 8
    assert updated["settings"]["similarity_threshold"] == 0.6
    assert updated["defaults"]["retrieval_top_k"] == 5

    reset = client.post("/api/settings/reset").json()
    assert reset["settings"] == reset["defaults"]


def test_settings_validation(client):
    res = client.put("/api/settings", json={"chunk_size": 200, "chunk_overlap": 300})
    assert res.status_code == 422 and "chunk_overlap" in res.json()["detail"]
    assert client.put("/api/settings", json={"similarity_threshold": 3}).status_code == 422
    assert client.put("/api/settings", json={"unknown": 1}).status_code == 422


def test_stale_documents_reported(ready_client):
    assert ready_client.get("/api/settings").json()["stale_documents"] == 0
    stale = ready_client.put("/api/settings", json={"chunk_size": 500}).json()["stale_documents"]
    assert stale == 2


def test_models_endpoint(client, fake_llm):
    body = client.get("/api/settings/models").json()
    assert body["available"] and body["models"][0]["name"] == "qwen2.5:3b"
    fake_llm.fail_with = "down"
    body = client.get("/api/settings/models").json()
    assert body["available"] is False and body["error"] == "down"


# ------------------------------------------------------------ stats/auth
def test_stats(ready_client):
    ready_client.post("/api/chat/ask", json={"question": "How many days of annual leave do employees get?"})
    ready_client.post("/api/chat/ask", json={"question": "What is the capital of Australia?"})
    stats = ready_client.get("/api/stats").json()
    assert stats["documents_total"] == 2
    assert stats["documents_by_status"] == {"ready": 2}
    assert stats["vector_count"] == stats["total_chunks"] > 0
    assert stats["questions_answered"] == 2
    assert stats["answers_by_type"] == {"grounded": 1, "no_context": 1}
    assert len(stats["recent_documents"]) == 2


def test_api_key_enforced(app_factory):
    client = app_factory(api_key="s3cret")
    assert client.get("/api/health").status_code == 200  # probes stay open
    assert client.get("/api/health/ready").status_code == 200
    assert client.get("/api/documents").status_code == 401
    assert client.get("/api/stats").status_code == 401
    assert client.get("/api/documents", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/api/documents", headers={"X-API-Key": "s3cret"}).status_code == 200
    assert client.get("/api/settings", headers={"Authorization": "Bearer s3cret"}).status_code == 200
    assert client.get("/api/settings").json() == {"detail": "Invalid or missing API key"}
