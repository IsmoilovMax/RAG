from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_container, get_session
from app.container import Container
from app.core.exceptions import ValidationError
from app.db.models import DocumentStatus
from app.schemas.document import (
    ChunkList,
    ChunkOut,
    DocumentList,
    DocumentOut,
    ReindexResponse,
    UploadResponse,
)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=UploadResponse, status_code=status.HTTP_200_OK)
async def upload_documents(
    files: list[UploadFile] = File(..., description="One or more documents"),
    container: Container = Depends(get_container),
) -> UploadResponse:
    limit = container.settings.max_files_per_upload
    if not files:
        raise ValidationError("No files provided")
    if len(files) > limit:
        raise ValidationError(f"Too many files: at most {limit} per upload")
    results = [await container.documents.upload(f) for f in files]
    return UploadResponse(
        results=results,
        accepted=sum(r.status == "accepted" for r in results),
        duplicates=sum(r.status == "duplicate" for r in results),
        rejected=sum(r.status == "rejected" for r in results),
    )


@router.get("", response_model=DocumentList)
def list_documents(
    status_filter: DocumentStatus | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> DocumentList:
    items, total = container.documents.list(
        session, status=status_filter, search=q, limit=limit, offset=offset
    )
    return DocumentList(items=[DocumentOut.model_validate(d) for d in items], total=total)


@router.post("/reindex", response_model=ReindexResponse)
def reindex_all(container: Container = Depends(get_container)) -> ReindexResponse:
    return ReindexResponse(queued=container.documents.reindex_all())


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: str,
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> DocumentOut:
    return DocumentOut.model_validate(container.documents.get(session, document_id))


@router.get("/{document_id}/chunks", response_model=ChunkList)
def get_document_chunks(
    document_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> ChunkList:
    doc = container.documents.get(session, document_id)
    rows = container.store.get_document_chunks(document_id, limit=limit, offset=offset)
    return ChunkList(
        items=[ChunkOut(**r) for r in rows], document_id=document_id, total=doc.chunk_count
    )


@router.get("/{document_id}/file")
def download_document(
    document_id: str,
    session: Session = Depends(get_session),
    container: Container = Depends(get_container),
) -> FileResponse:
    doc = container.documents.get(session, document_id)
    path = container.documents.file_path(doc)
    return FileResponse(path, media_type=doc.mime_type or "application/octet-stream", filename=doc.filename)


@router.post("/{document_id}/reprocess", response_model=DocumentOut)
def reprocess_document(document_id: str, container: Container = Depends(get_container)) -> DocumentOut:
    return DocumentOut.model_validate(container.documents.reprocess(document_id))


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: str, container: Container = Depends(get_container)) -> None:
    container.documents.delete(document_id)
