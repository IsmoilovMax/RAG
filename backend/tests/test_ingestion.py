"""Background ingestion pipeline behaviour."""

from __future__ import annotations

import hashlib

from app.db.models import Document, DocumentStatus
from app.services.ingestion import embedding_text
from tests.conftest import add_document


def _get(container, doc_id):
    with container.db.session() as s:
        return s.get(Document, doc_id)


def test_successful_ingestion_records_metadata(container, sample_dir):
    doc_id = add_document(container, sample_dir / "q3_sales_report.xlsx")
    doc = _get(container, doc_id)
    assert doc.status == DocumentStatus.READY
    assert doc.progress == 100
    assert doc.chunk_count == container.store.count() > 0
    assert doc.page_count == 2
    assert doc.chunk_size == container.settings.chunk_size
    assert doc.embedding_model == "test-hash-embedder"
    assert doc.processing_ms is not None and doc.processed_at is not None


def test_reprocessing_is_idempotent(container, sample_dir):
    doc_id = add_document(container, sample_dir / "support_faq.txt")
    first = container.store.count()
    container.ingestion.process(doc_id)
    assert container.store.count() == first


def test_failed_parse_marks_document_failed(container, tmp_path):
    bad = tmp_path / "broken.docx"
    bad.write_bytes(b"PK\x03\x04 this is not really a docx")
    doc_id = add_document(container, bad)
    doc = _get(container, doc_id)
    assert doc.status == DocumentStatus.FAILED
    assert doc.error_message
    assert container.store.count() == 0


def test_document_without_text_fails_with_hint(container, tmp_path):
    import pymupdf

    path = tmp_path / "blank.pdf"
    pdf = pymupdf.open()
    pdf.new_page()
    pdf.save(path)
    pdf.close()
    doc = _get(container, add_document(container, path))
    assert doc.status == DocumentStatus.FAILED
    assert "OCR" in doc.error_message


def test_chunk_settings_from_runtime_are_used(container, sample_dir):
    from app.schemas.settings import RuntimeSettingsUpdate

    with container.db.session() as s:
        container.settings_service.update(s, RuntimeSettingsUpdate(chunk_size=200, chunk_overlap=20))
    doc = _get(container, add_document(container, sample_dir / "support_faq.txt"))
    assert (doc.chunk_size, doc.chunk_overlap) == (200, 20)
    assert doc.chunk_count > 3


def test_resume_pending_requeues_interrupted_jobs(container, sample_dir):
    path = sample_dir / "inventory.csv"
    data = path.read_bytes()
    with container.db.session() as s:
        doc = Document(filename=path.name, stored_name="", file_type="csv", size_bytes=len(data),
                       sha256=hashlib.sha256(data).hexdigest(), status=DocumentStatus.PROCESSING)
        s.add(doc)
        s.flush()
        doc.stored_name = f"{doc.id}.csv"
        doc_id = doc.id
    (container.settings.upload_dir / f"{doc_id}.csv").write_bytes(data)
    assert container.ingestion.resume_pending() == 1
    container.ingestion.wait_idle(30)
    assert _get(container, doc_id).status == DocumentStatus.READY


def test_missing_document_is_ignored(container):
    container.ingestion.process("does-not-exist")  # must not raise


def test_embedding_text_adds_context_header():
    assert embedding_text("q3_sales_report.xlsx", "Sheet: Targets", "Region: X") == "q3 sales report — Sheet: Targets\nRegion: X"
    assert embedding_text("spec.docx", "Overview", "Overview\nBody") == "spec\nOverview\nBody"
