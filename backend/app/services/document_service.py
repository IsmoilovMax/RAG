"""Document management: secure uploads, de-duplication, listing and deletion."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import tempfile
import unicodedata
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import AppError, NotFoundError, PayloadTooLargeError
from app.db.models import Document, DocumentStatus
from app.db.session import Database
from app.schemas.document import DocumentOut, UploadResult
from app.services.ingestion import IngestionService
from app.services.parsing import SUPPORTED_TYPES, detect_file_type, validate_content
from app.services.vector_store import ChromaVectorStore

logger = logging.getLogger(__name__)

_READ_CHUNK = 1024 * 1024
_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_filename(name: str | None) -> str:
    name = unicodedata.normalize("NFKC", name or "").replace("\\", "/")
    name = os.path.basename(name).strip().strip(".")
    name = _UNSAFE_CHARS.sub("_", name)
    if not name:
        name = "document"
    stem, dot, ext = name.rpartition(".")
    if dot and len(name) > 200:
        name = f"{stem[: 200 - len(ext) - 1]}.{ext}"
    return name[:200]


class DocumentService:
    def __init__(
        self,
        *,
        db: Database,
        settings: Settings,
        store: ChromaVectorStore,
        ingestion: IngestionService,
    ) -> None:
        self.db = db
        self.settings = settings
        self.store = store
        self.ingestion = ingestion

    # --------------------------------------------------------------- uploads
    async def _spool(self, upload: UploadFile) -> tuple[Path, str, int]:
        """Stream the upload to a temp file, enforcing the size limit and hashing it."""
        limit = self.settings.max_upload_bytes
        digest = hashlib.sha256()
        size = 0
        fd, tmp_name = tempfile.mkstemp(dir=self.settings.upload_dir, suffix=".part")
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as out:
                while chunk := await upload.read(_READ_CHUNK):
                    size += len(chunk)
                    if size > limit:
                        raise PayloadTooLargeError(
                            f"File exceeds the {self.settings.max_upload_mb} MB upload limit"
                        )
                    digest.update(chunk)
                    out.write(chunk)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise
        return tmp_path, digest.hexdigest(), size

    async def upload(self, upload: UploadFile) -> UploadResult:
        filename = sanitize_filename(upload.filename)
        tmp_path: Path | None = None
        try:
            file_type = detect_file_type(filename)
            tmp_path, sha256, size = await self._spool(upload)
            if size == 0:
                raise AppError("File is empty")
            validate_content(tmp_path, file_type)

            with self.db.session() as session:
                existing = session.scalar(select(Document).where(Document.sha256 == sha256))
                if existing is not None:
                    return UploadResult(
                        filename=filename,
                        status="duplicate",
                        document=DocumentOut.model_validate(existing),
                        error=f"Identical file already uploaded as '{existing.filename}'",
                    )
                doc = Document(
                    filename=filename,
                    stored_name="",
                    file_type=file_type,
                    mime_type=SUPPORTED_TYPES[file_type][0],
                    size_bytes=size,
                    sha256=sha256,
                    status=DocumentStatus.PENDING,
                )
                session.add(doc)
                session.flush()
                doc.stored_name = f"{doc.id}.{file_type}"
                final_path = self.settings.upload_dir / doc.stored_name
                os.replace(tmp_path, final_path)
                tmp_path = None
                result = DocumentOut.model_validate(doc)
        except IntegrityError:
            # Concurrent upload of identical content won the unique-constraint race.
            return UploadResult(filename=filename, status="duplicate", error="Identical file already uploaded")
        except AppError as exc:
            return UploadResult(filename=filename, status="rejected", error=exc.message)
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)
            await upload.close()

        self.ingestion.submit(result.id)
        logger.info("Document accepted", extra={"document_id": result.id, "doc_filename": filename, "bytes": size})
        return UploadResult(filename=filename, status="accepted", document=result)

    # ----------------------------------------------------------------- reads
    def list(
        self,
        session: Session,
        *,
        status: DocumentStatus | None = None,
        search: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[list[Document], int]:
        query = select(Document)
        if status is not None:
            query = query.where(Document.status == status)
        if search:
            like = f"%{search.lower()}%"
            query = query.where(or_(func.lower(Document.filename).like(like), Document.file_type == search.lower()))
        total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
        items = session.scalars(
            query.order_by(Document.created_at.desc()).limit(limit).offset(offset)
        ).all()
        return list(items), int(total)

    def get(self, session: Session, document_id: str) -> Document:
        doc = session.get(Document, document_id)
        if doc is None:
            raise NotFoundError("Document not found")
        return doc

    def file_path(self, doc: Document) -> Path:
        path = (self.settings.upload_dir / doc.stored_name).resolve()
        if self.settings.upload_dir.resolve() not in path.parents or not path.exists():
            raise NotFoundError("Stored file not found")
        return path

    # ---------------------------------------------------------------- writes
    def delete(self, document_id: str) -> None:
        with self.db.session() as session:
            doc = self.get(session, document_id)
            stored_name = doc.stored_name
            session.delete(doc)
        self.store.delete_document(document_id)
        if stored_name:
            (self.settings.upload_dir / stored_name).unlink(missing_ok=True)
        logger.info("Document deleted", extra={"document_id": document_id})

    def reprocess(self, document_id: str) -> Document:
        with self.db.session() as session:
            doc = self.get(session, document_id)
            if doc.status == DocumentStatus.PROCESSING:
                raise AppError("Document is already being processed")
            doc.status = DocumentStatus.PENDING
            doc.progress = 0
            doc.error_message = None
        self.ingestion.submit(document_id)
        with self.db.session() as session:
            return self.get(session, document_id)

    def reindex_all(self) -> int:
        with self.db.session() as session:
            docs = session.scalars(
                select(Document).where(Document.status != DocumentStatus.PROCESSING)
            ).all()
            ids = [d.id for d in docs]
            for doc in docs:
                doc.status = DocumentStatus.PENDING
                doc.progress = 0
                doc.error_message = None
        for doc_id in ids:
            self.ingestion.submit(doc_id)
        return len(ids)
