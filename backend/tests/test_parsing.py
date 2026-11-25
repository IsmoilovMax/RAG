"""Document parsing and upload content validation."""

from __future__ import annotations

import pymupdf
import pytest

from app.core.exceptions import DocumentParseError, ValidationError
from app.services.parsing import detect_file_type, parse_document, validate_content


def _all_text(parsed) -> str:
    return "\n".join(s.text for s in parsed.sections)


def test_pdf_pages_are_preserved(sample_dir):
    parsed = parse_document(sample_dir / "employee_handbook.pdf", "pdf")
    assert parsed.page_count == 3
    assert [s.page for s in parsed.sections] == [1, 2, 3]
    assert "28 days of paid annual leave" in parsed.sections[1].text.replace("\n", " ")
    assert "Mara Lindqvist" in parsed.sections[0].text


def test_docx_headings_tables_and_order(sample_dir):
    parsed = parse_document(sample_dir / "atlas_x2_specification.docx", "docx")
    text = _all_text(parsed)
    assert "55 minutes" in text
    # Tables are rendered as self-describing rows.
    assert "Model: Atlas X2 Pro | Payload: 600 kg" in text
    sections = {s.section for s in parsed.sections}
    assert {"Battery and Charging", "Model Comparison"} <= sections


def test_xlsx_sheets_become_sections(sample_dir):
    parsed = parse_document(sample_dir / "q3_sales_report.xlsx", "xlsx")
    assert parsed.is_tabular
    assert parsed.page_count == 2
    labels = [s.section for s in parsed.sections]
    assert labels == ["Sheet: Regional Sales", "Sheet: Q4 Targets"]
    assert "Region: DACH | Q3 Revenue (EUR): 3150000" in parsed.sections[0].text
    assert "Sales Lead: Lucia Moreno" in parsed.sections[1].text


def test_pptx_slides_and_notes(sample_dir):
    parsed = parse_document(sample_dir / "onboarding_presentation.pptx", "pptx")
    assert parsed.page_count == 3
    slide2 = parsed.sections[1]
    assert slide2.page == 2
    assert slide2.section == "Slide 2: Your First Week"
    assert "Building C reception" in slide2.text
    assert "Speaker notes: Remind new hires" in slide2.text


def test_txt_and_csv(sample_dir):
    txt = parse_document(sample_dir / "support_faq.txt", "txt")
    assert "3-year warranty" in _all_text(txt)
    csv = parse_document(sample_dir / "inventory.csv", "csv")
    assert csv.is_tabular
    assert "SKU: NW-1003 | Part: LFP battery pack | Stock: 57" in _all_text(csv)


def test_text_encoding_fallback(tmp_path):
    path = tmp_path / "latin.txt"
    path.write_bytes("Café crème — prix: 5€".encode("cp1252"))
    assert "Café crème" in _all_text(parse_document(path, "txt"))


def test_csv_semicolon_dialect(tmp_path):
    path = tmp_path / "semi.csv"
    path.write_text("name;city\nAda;London\nAlan;Wilmslow\n", encoding="utf-8")
    assert "name: Alan | city: Wilmslow" in _all_text(parse_document(path, "csv"))


@pytest.mark.parametrize(
    ("name", "expected"),
    [("report.PDF", "pdf"), ("a.b.docx", "docx"), ("data.xlsx", "xlsx"), ("notes.md", "md")],
)
def test_detect_file_type(name, expected):
    assert detect_file_type(name) == expected


@pytest.mark.parametrize("name", ["malware.exe", "archive.zip", "noext", "image.png"])
def test_detect_rejects_unsupported(name):
    with pytest.raises(ValidationError):
        detect_file_type(name)


def test_validate_rejects_spoofed_pdf(tmp_path):
    fake = tmp_path / "fake.pdf"
    fake.write_text("I am not a PDF")
    with pytest.raises(ValidationError, match="not a valid PDF"):
        validate_content(fake, "pdf")


def test_validate_rejects_zip_without_office_part(tmp_path):
    import zipfile

    path = tmp_path / "fake.docx"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("hello.txt", "hi")
    with pytest.raises(ValidationError, match="not a valid .docx"):
        validate_content(path, "docx")


def test_validate_rejects_binary_text_and_empty(tmp_path):
    binary = tmp_path / "bin.txt"
    binary.write_bytes(b"\x00\x01\x02binary\x00")
    with pytest.raises(ValidationError):
        validate_content(binary, "txt")
    empty = tmp_path / "empty.txt"
    empty.write_bytes(b"")
    with pytest.raises(ValidationError, match="empty"):
        validate_content(empty, "txt")


def test_validate_accepts_real_samples(sample_dir):
    for path in sample_dir.iterdir():
        validate_content(path, detect_file_type(path.name))


def test_truncated_pdf_raises_parse_error(tmp_path, sample_dir):
    data = (sample_dir / "employee_handbook.pdf").read_bytes()
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(data[:200])
    try:
        parsed = parse_document(broken, "pdf")
    except DocumentParseError:
        return
    # PyMuPDF may repair some damage; if it does, there must be no usable text.
    assert not parsed.has_text


def test_corrupt_office_file_raises_parse_error(tmp_path):
    bad = tmp_path / "bad.pptx"
    bad.write_bytes(b"PK\x03\x04garbage")
    with pytest.raises(DocumentParseError):
        parse_document(bad, "pptx")


def test_encrypted_pdf_is_rejected(tmp_path):
    path = tmp_path / "secret.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "secret")
    doc.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="owner")
    doc.close()
    with pytest.raises(DocumentParseError, match="password"):
        parse_document(path, "pdf")
