from __future__ import annotations

import asyncio
from collections import Counter

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from app.api.deps import get_container
from app.container import Container
from app.core.security import require_api_key
from app.db.models import Conversation, Document, Message
from app.schemas.common import as_utc_iso
from app.schemas.system import ComponentHealth, ReadinessResponse, StatsResponse

health_router = APIRouter(prefix="/health", tags=["health"])
stats_router = APIRouter(tags=["system"], dependencies=[Depends(require_api_key)])


@health_router.get("")
def liveness() -> dict[str, str]:
    """Liveness probe: the process is up and serving requests."""
    return {"status": "ok"}


@health_router.get("/ready", response_model=ReadinessResponse)
async def readiness(request: Request) -> JSONResponse:
    """Readiness probe: checks the database, vector store, embeddings and LLM."""
    container: Container = request.app.state.container
    components: dict[str, ComponentHealth] = {}

    try:
        await asyncio.to_thread(container.db.ping)
        components["database"] = ComponentHealth(status="ok", info={"backend": container.db.engine.dialect.name})
    except Exception as exc:
        components["database"] = ComponentHealth(status="error", detail=str(exc))

    try:
        count = await asyncio.to_thread(container.store.count)
        components["vector_store"] = ComponentHealth(status="ok", info={"vectors": count})
    except Exception as exc:
        components["vector_store"] = ComponentHealth(status="error", detail=str(exc))

    components["embeddings"] = ComponentHealth(
        status="ok" if container.embedder.is_loaded else "degraded",
        detail=None if container.embedder.is_loaded else "Model loads on first use",
        info={"model": container.embedder.model_name},
    )

    with container.db.session() as session:
        model = container.settings_service.get(session).llm_model
    try:
        version = await container.llm.health()
        models = await container.llm.list_models()
        names = {m["name"] for m in models}
        installed = model in names or f"{model}:latest" in names
        components["llm"] = ComponentHealth(
            status="ok" if installed else "degraded",
            detail=None if installed else f"Model '{model}' is not pulled. Run: ollama pull {model}",
            info={"model": model, "ollama_version": version.get("version"), "installed_models": sorted(names)},
        )
    except Exception as exc:
        components["llm"] = ComponentHealth(
            status="error", detail=f"Ollama unreachable: {exc}", info={"model": model}
        )

    statuses = {c.status for c in components.values()}
    if components["database"].status == "error" or components["vector_store"].status == "error":
        overall = "error"
    elif statuses == {"ok"}:
        overall = "ok"
    else:
        overall = "degraded"
    body = ReadinessResponse(status=overall, components=components)
    return JSONResponse(status_code=200 if overall != "error" else 503, content=body.model_dump(mode="json"))


@stats_router.get("/stats", response_model=StatsResponse)
def stats(container: Container = Depends(get_container)) -> StatsResponse:
    with container.db.session() as session:
        docs = session.scalars(select(Document).order_by(Document.created_at.desc())).all()
        assistant_meta = session.scalars(select(Message.meta).where(Message.role == "assistant")).all()
        conversations = session.scalar(select(func.count(Conversation.id))) or 0
        messages = session.scalar(select(func.count(Message.id))) or 0

    by_status = Counter(d.status.value for d in docs)
    by_type = Counter(d.file_type for d in docs)
    answer_types = Counter((m or {}).get("answer_type", "unknown") for m in assistant_meta)
    latencies = [m["latency_ms"] for m in assistant_meta if m and isinstance(m.get("latency_ms"), int)]
    try:
        vector_count = container.store.count()
    except Exception:
        vector_count = 0
    return StatsResponse(
        documents_total=len(docs),
        documents_by_status=dict(by_status),
        documents_by_type=dict(by_type),
        total_chunks=sum(d.chunk_count for d in docs),
        vector_count=vector_count,
        total_size_bytes=sum(d.size_bytes for d in docs),
        conversations=int(conversations),
        messages=int(messages),
        questions_answered=len(assistant_meta),
        answers_by_type=dict(answer_types),
        avg_latency_ms=round(sum(latencies) / len(latencies), 1) if latencies else None,
        processing_queue=container.ingestion.active_count(),
        recent_documents=[
            {
                "id": d.id,
                "filename": d.filename,
                "file_type": d.file_type,
                "status": d.status.value,
                "chunk_count": d.chunk_count,
                "created_at": as_utc_iso(d.created_at),
            }
            for d in docs[:6]
        ],
    )
