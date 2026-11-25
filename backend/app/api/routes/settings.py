from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_container, get_session
from app.container import Container
from app.core.exceptions import AppError
from app.db.models import Document, DocumentStatus
from app.schemas.settings import (
    ModelsResponse,
    OllamaModel,
    RuntimeSettingsUpdate,
    SettingsResponse,
    SystemInfo,
)
from app.services.parsing import SUPPORTED_TYPES

router = APIRouter(prefix="/settings", tags=["settings"])


def _response(session: Session, container: Container) -> SettingsResponse:
    s = container.settings
    runtime = container.settings_service.get(session)
    # Ready documents chunked with different parameters than the current ones.
    stale = session.scalar(
        select(func.count(Document.id)).where(
            Document.status == DocumentStatus.READY,
            or_(Document.chunk_size != runtime.chunk_size, Document.chunk_overlap != runtime.chunk_overlap),
        )
    )
    return SettingsResponse(
        settings=runtime,
        defaults=container.settings_service.defaults(),
        system=SystemInfo(
            app_name=s.app_name,
            environment=s.environment,
            embedding_model=s.embedding_model,
            embedding_batch_size=s.embedding_batch_size,
            ollama_base_url=s.ollama_base_url,
            ollama_num_ctx=s.ollama_num_ctx,
            max_upload_mb=s.max_upload_mb,
            max_files_per_upload=s.max_files_per_upload,
            supported_types=sorted(SUPPORTED_TYPES),
            auth_enabled=s.api_key is not None,
            database_backend=container.db.engine.dialect.name,
        ),
        stale_documents=int(stale or 0),
    )


@router.get("", response_model=SettingsResponse)
def get_settings(session: Session = Depends(get_session), container: Container = Depends(get_container)) -> SettingsResponse:
    return _response(session, container)


@router.put("", response_model=SettingsResponse)
def update_settings(
    body: RuntimeSettingsUpdate,
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> SettingsResponse:
    container.settings_service.update(session, body)
    return _response(session, container)


@router.post("/reset", response_model=SettingsResponse)
def reset_settings(session: Session = Depends(get_session), container: Container = Depends(get_container)) -> SettingsResponse:
    container.settings_service.reset(session)
    return _response(session, container)


@router.get("/models", response_model=ModelsResponse)
async def list_models(container: Container = Depends(get_container)) -> ModelsResponse:
    with container.db.session() as session:
        current = container.settings_service.get(session).llm_model
    try:
        models = await container.llm.list_models()
    except AppError as exc:
        return ModelsResponse(available=False, current=current, error=exc.message)
    return ModelsResponse(available=True, current=current, models=[OllamaModel(**m) for m in models])
