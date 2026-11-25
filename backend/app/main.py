"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.api.router import api_router
from app.container import Container, build_container
from app.core.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.security import SecurityHeadersMiddleware

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    *,
    container_factory: Callable[[Settings], Container] | None = None,
    warmup: bool = True,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container = (container_factory or build_container)(settings)
        app.state.container = container
        container.ingestion.resume_pending()
        warm_task = None
        if warmup:
            # Load the embedding model in the background so the first request is fast.
            warm_task = asyncio.create_task(asyncio.to_thread(_warmup, container))
        logger.info(
            "Application started",
            extra={"env": settings.environment, "db": container.db.engine.dialect.name, "llm": settings.ollama_model},
        )
        try:
            yield
        finally:
            if warm_task is not None and not warm_task.done():
                warm_task.cancel()
            await container.aclose()
            logger.info("Application stopped")

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description="CPU-only Retrieval-Augmented Generation API",
        lifespan=lifespan,
        docs_url=f"{settings.api_prefix}/docs",
        openapi_url=f"{settings.api_prefix}/openapi.json",
        redoc_url=None,
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-API-Key", "Authorization"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


def _warmup(container: Container) -> None:
    warm = getattr(container.embedder, "warmup", None)
    if warm is None:
        return
    try:
        warm()
    except Exception:
        logger.exception("Embedding model warm-up failed")


app = create_app()
