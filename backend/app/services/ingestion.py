"""Background document ingestion: parse -> clean -> chunk -> embed -> store."""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, wait
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.core.config import Settings
from app.core.exceptions import AppError
from app.db.models import Document, DocumentStatus
from app.db.session import Database
from app.services.chunking import chunk_document
from app.services.embeddings import Embedder
from app.services.parsing import ParsedSection, parse_document
from app.services.settings_service import SettingsService
from app.services.text_cleaning import clean_text
from app.services.vector_store import ChromaVectorStore, VectorRecord

logger = logging.getLogger(__name__)

EMBED_BATCH_CHUNKS = 64
_MERGE_LINE_TYPES = {"pdf", "pptx", "txt", "md"}


class _Cancelled(Exception):
    """The document was deleted while it was being processed."""


def embedding_text(filename: str, section: str | None, text: str) -> str:
    """Prefix chunk text with a light document/section header before embedding.

    The header gives isolated chunks (table rows, later paragraphs of a section)
    the context they need to match queries; the stored text stays unchanged.
    """
    title = Path(filename).stem.replace("_", " ").replace("-", " ").strip()
    header = f"{title} — {section}" if section else title
    if section and text.startswith(section):
        header = title
    return f"{header}\n{text}"


class IngestionService:
    def __init__(
        self,
        *,
        db: Database,
        settings: Settings,
        settings_service: SettingsService,
        embedder: Embedder,
        store: ChromaVectorStore,
    ) -> None:
        self.db = db
        self.settings = settings
        self.settings_service = settings_service
        self.embedder = embedder
        self.store = store
        self._executor = ThreadPoolExecutor(
            max_workers=settings.ingestion_workers, thread_name_prefix="ingest"
        )
        self._futures: dict[str, Future] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ queue
    def submit(self, document_id: str) -> None:
        with self._lock:
            existing = self._futures.get(document_id)
            if existing is not None and not existing.done():
                return
            future = self._executor.submit(self._run, document_id)
            self._futures[document_id] = future
            future.add_done_callback(lambda _f, d=document_id: self._forget(d, _f))

    def _forget(self, document_id: str, future: Future) -> None:
        with self._lock:
            if self._futures.get(document_id) is future:
                del self._futures[document_id]

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for f in self._futures.values() if not f.done())

    def resume_pending(self) -> int:
        """Re-queue documents left pending/processing by a previous run."""
        with self.db.session() as session:
            docs = session.scalars(
                select(Document).where(
                    Document.status.in_([DocumentStatus.PENDING, DocumentStatus.PROCESSING])
                )
            ).all()
            ids = [d.id for d in docs]
            for doc in docs:
                doc.status = DocumentStatus.PENDING
                doc.progress = 0
        for doc_id in ids:
            self.submit(doc_id)
        if ids:
            logger.info("Resumed pending ingestion jobs", extra={"count": len(ids)})
        return len(ids)

    def wait_idle(self, timeout: float | None = None) -> None:
        with self._lock:
            pending = list(self._futures.values())
        if pending:
            wait(pending, timeout=timeout)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    # --------------------------------------------------------------- pipeline
    def _update(self, document_id: str, **fields) -> None:
        with self.db.session() as session:
            doc = session.get(Document, document_id)
            if doc is None:
                raise _Cancelled
            for key, value in fields.items():
                setattr(doc, key, value)

    def _run(self, document_id: str) -> None:
        try:
            self.process(document_id)
        except Exception:  # never let a worker thread die silently
            logger.exception("Ingestion crashed", extra={"document_id": document_id})

    def process(self, document_id: str) -> None:
        started = time.perf_counter()
        with self.db.session() as session:
            doc = session.get(Document, document_id)
            if doc is None:
                return
            file_type, filename, stored_name = doc.file_type, doc.filename, doc.stored_name
            doc.status = DocumentStatus.PROCESSING
            doc.progress = 5
            doc.error_message = None

        log_extra = {"document_id": document_id, "doc_filename": filename}
        logger.info("Ingestion started", extra=log_extra)
        try:
            runtime = self._runtime()
            path = self.settings.upload_dir / stored_name
            if not path.exists():
                raise AppError("Stored file is missing from disk")

            parsed = parse_document(Path(path), file_type)
            merge = file_type in _MERGE_LINE_TYPES
            parsed.sections = [
                ParsedSection(text=clean_text(s.text, merge_lines=merge), page=s.page, section=s.section)
                for s in parsed.sections
            ]
            if not parsed.has_text:
                hint = " Scanned PDFs need OCR, which is not supported." if file_type == "pdf" else ""
                raise AppError(f"No extractable text found in document.{hint}")
            self._update(document_id, progress=20, page_count=parsed.page_count, char_count=parsed.char_count)

            chunks = chunk_document(
                parsed, chunk_size=runtime.chunk_size, chunk_overlap=runtime.chunk_overlap
            )
            if not chunks:
                raise AppError("Document produced no usable text chunks")
            self._update(document_id, progress=30)

            # Idempotent: remove any vectors from a previous run before re-adding.
            self.store.delete_document(document_id)
            total = len(chunks)
            for start in range(0, total, EMBED_BATCH_CHUNKS):
                batch = chunks[start : start + EMBED_BATCH_CHUNKS]
                vectors = self.embedder.embed_documents(
                    [embedding_text(filename, c.section, c.text) for c in batch]
                )
                self.store.add(
                    [
                        VectorRecord(
                            id=f"{document_id}:{c.index}",
                            text=c.text,
                            embedding=vec,
                            metadata={
                                "document_id": document_id,
                                "filename": filename,
                                "file_type": file_type,
                                "page": c.page,
                                "section": c.section,
                                "chunk_index": c.index,
                            },
                        )
                        for c, vec in zip(batch, vectors, strict=True)
                    ]
                )
                done = min(start + EMBED_BATCH_CHUNKS, total)
                self._update(document_id, progress=30 + int(65 * done / total))

            elapsed_ms = int((time.perf_counter() - started) * 1000)
            self._update(
                document_id,
                status=DocumentStatus.READY,
                progress=100,
                chunk_count=total,
                chunk_size=runtime.chunk_size,
                chunk_overlap=runtime.chunk_overlap,
                embedding_model=self.embedder.model_name,
                processing_ms=elapsed_ms,
                processed_at=datetime.now(UTC),
            )
            logger.info("Ingestion finished", extra={**log_extra, "chunks": total, "ms": elapsed_ms})
        except _Cancelled:
            self.store.delete_document(document_id)
            logger.info("Ingestion cancelled (document deleted)", extra=log_extra)
        except Exception as exc:
            message = exc.message if isinstance(exc, AppError) else f"Unexpected error: {exc}"
            if not isinstance(exc, AppError):
                logger.exception("Ingestion failed", extra=log_extra)
            else:
                logger.warning("Ingestion failed", extra={**log_extra, "error": message})
            try:
                self.store.delete_document(document_id)
            except Exception:  # pragma: no cover - best-effort cleanup
                logger.exception("Vector cleanup failed", extra=log_extra)
            try:
                self._update(
                    document_id,
                    status=DocumentStatus.FAILED,
                    error_message=message[:2000],
                    progress=0,
                    chunk_count=0,
                )
            except _Cancelled:
                pass

    def _runtime(self):
        with self.db.session() as session:
            return self.settings_service.get(session)
