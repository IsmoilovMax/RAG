"""Generate sample documents (PDF, DOCX, XLSX, PPTX, TXT, CSV) about a fictional company.

The facts are invented, so a model cannot answer from prior knowledge: correct
answers prove that retrieval works.

Usage:  python scripts/generate_samples.py [output_dir]   (default: ../samples)
"""

from __future__ import annotations

import sys
from pathlib import Path

HANDBOOK_PAGES = [
    (
        "Northwind Robotics Employee Handbook\n\n"
        "1. Company Overview\n"
        "Northwind Robotics was founded in 2014 in Tallinn, Estonia, by Mara Lindqvist. "
        "The company designs autonomous warehouse robots and employs 340 people across "
        "offices in Tallinn, Helsinki and Rotterdam. Our mission is to make warehouse "
        "logistics safer and more efficient through reliable automation."
    ),
    (
        "2. Leave Policy\n"
        "Every full-time employee receives 28 days of paid annual leave per calendar year. "
        "Up to 5 unused days may be carried over into the next year, but carried-over days "
        "must be used before March 31. Parental leave is 18 weeks at full pay for all parents. "
        "Sick leave requires a doctor's certificate after 3 consecutive days of absence."
    ),
    (
        "3. Remote Work and Equipment\n"
        "Employees may work remotely up to 3 days per week with manager approval. "
        "Core collaboration hours are 10:00 to 15:00 Tallinn time. Each employee receives a "
        "home-office equipment stipend of 600 euros every two years. Company laptops must be "
        "encrypted and returned within 5 working days after the end of employment."
    ),
]

PRODUCT_PARAGRAPHS = [
    ("Title", "Atlas X2 Warehouse Robot — Technical Specification"),
    ("Heading 1", "Overview"),
    (
        None,
        "The Atlas X2 is an autonomous mobile robot for pallet transport in warehouses. "
        "It navigates using a 360-degree LiDAR sensor with a range of 30 metres and "
        "reaches a maximum speed of 2.1 metres per second.",
    ),
    ("Heading 1", "Battery and Charging"),
    (
        None,
        "The lithium iron phosphate battery provides 8 hours of continuous runtime. "
        "Fast charging from 0 to 80 percent takes 55 minutes at a Northwind DockStation.",
    ),
    ("Heading 1", "Safety"),
    (
        None,
        "The robot stops automatically when an obstacle is detected within 0.5 metres. "
        "It is certified to ISO 3691-4 for driverless industrial trucks.",
    ),
    ("Heading 1", "Model Comparison"),
]

PRODUCT_TABLE = [
    ["Model", "Payload", "Runtime", "Price (EUR)"],
    ["Atlas X1", "300 kg", "6 hours", "38,000"],
    ["Atlas X2", "450 kg", "8 hours", "52,000"],
    ["Atlas X2 Pro", "600 kg", "10 hours", "67,500"],
]

SALES_SHEETS = {
    "Regional Sales": [
        ["Region", "Q3 Revenue (EUR)", "Units Sold", "Top Product"],
        ["Nordics", 4200000, 81, "Atlas X2"],
        ["DACH", 3150000, 60, "Atlas X2 Pro"],
        ["Benelux", 1870000, 36, "Atlas X2"],
        ["Iberia", 960000, 25, "Atlas X1"],
    ],
    "Q4 Targets": [
        ["Region", "Q4 Target (EUR)", "Sales Lead"],
        ["Nordics", 4800000, "Johan Berg"],
        ["DACH", 3600000, "Klara Weiss"],
        ["Benelux", 2100000, "Pieter de Vries"],
        ["Iberia", 1200000, "Lucia Moreno"],
    ],
}

ONBOARDING_SLIDES = [
    ("Welcome to Northwind Robotics", ["Your onboarding guide for the first week"], None),
    (
        "Your First Week",
        [
            "Day 1: Pick up your laptop at Building C reception at 09:00",
            "Day 2: Mandatory robot safety training in Lab 2",
            "Day 3: Shadow a senior engineer on the warehouse floor",
            "Day 5: Lunch with your team and onboarding buddy",
        ],
        "Remind new hires to bring a photo ID on day 1.",
    ),
    (
        "Key Contacts",
        [
            "IT helpdesk: extension 4400",
            "HR team: hr@northwind.example",
            "Facilities and access badges: extension 4120",
        ],
        None,
    ),
]

FAQ_TEXT = """Northwind Robotics Customer Support FAQ

Q: How long is the warranty on Atlas robots?
A: All Atlas robots include a 3-year warranty covering parts and labour. An extended
warranty of up to 5 years can be purchased within the first 12 months.

Q: How fast does support respond?
A: Critical tickets (robot fleet stopped) receive a response within 2 hours, 24/7.
Standard tickets receive a response within 1 business day.

Q: How often is firmware updated?
A: Firmware updates are released monthly on the first Tuesday of each month and are
installed automatically during the configured maintenance window.

Q: How do I contact support?
A: Email support@northwind.example or call +372 600 4400.
"""

INVENTORY_ROWS = [
    ["SKU", "Part", "Stock", "Warehouse", "Reorder Level"],
    ["NW-1001", "LiDAR sensor", "128", "Tallinn", "40"],
    ["NW-1002", "Drive motor", "312", "Rotterdam", "100"],
    ["NW-1003", "LFP battery pack", "57", "Tallinn", "60"],
    ["NW-1004", "Bumper safety strip", "890", "Helsinki", "200"],
]

EXAMPLE_QUESTIONS = [
    ("How many days of annual leave do employees get?", "employee_handbook.pdf", "28 days"),
    ("Until when must carried-over leave days be used?", "employee_handbook.pdf", "March 31"),
    ("How much is the home-office equipment stipend?", "employee_handbook.pdf", "600 euros"),
    ("What is the payload of the Atlas X2 Pro?", "atlas_x2_specification.docx", "600 kg"),
    ("How long does fast charging to 80 percent take?", "atlas_x2_specification.docx", "55 minutes"),
    ("What was the Q3 revenue in the DACH region?", "q3_sales_report.xlsx", "3150000"),
    ("Who is the sales lead for Iberia?", "q3_sales_report.xlsx", "Lucia Moreno"),
    ("Where do new hires pick up their laptop on day 1?", "onboarding_presentation.pptx", "Building C"),
    ("What is the IT helpdesk extension?", "onboarding_presentation.pptx", "4400"),
    ("How long is the warranty on Atlas robots?", "support_faq.txt", "3-year"),
    ("When are firmware updates released?", "support_faq.txt", "first Tuesday"),
    ("How many LFP battery packs are in stock?", "inventory.csv", "57"),
]

# Questions the documents cannot answer (the assistant must refuse).
UNANSWERABLE_QUESTIONS = [
    "What is the capital of Australia?",
    "Who won the 1998 FIFA World Cup?",
    "What is the recipe for chocolate chip cookies?",
]


def write_pdf(path: Path) -> None:
    import pymupdf

    doc = pymupdf.open()
    for text in HANDBOOK_PAGES:
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(60, 60, 540, 780), text, fontsize=11, fontname="helv")
    doc.set_metadata({"title": "Northwind Robotics Employee Handbook"})
    doc.save(path)
    doc.close()


def write_docx(path: Path) -> None:
    import docx

    document = docx.Document()
    for style, text in PRODUCT_PARAGRAPHS:
        if style == "Title":
            document.add_heading(text, level=0)
        elif style == "Heading 1":
            document.add_heading(text, level=1)
        else:
            document.add_paragraph(text)
    table = document.add_table(rows=0, cols=len(PRODUCT_TABLE[0]))
    for row in PRODUCT_TABLE:
        cells = table.add_row().cells
        for cell, value in zip(cells, row, strict=True):
            cell.text = value
    document.save(path)


def write_xlsx(path: Path) -> None:
    from openpyxl import Workbook

    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, rows in SALES_SHEETS.items():
        sheet = workbook.create_sheet(name)
        for row in rows:
            sheet.append(row)
    workbook.save(path)


def write_pptx(path: Path) -> None:
    from pptx import Presentation

    presentation = Presentation()
    for title, bullets, notes in ONBOARDING_SLIDES:
        slide = presentation.slides.add_slide(presentation.slide_layouts[1])
        slide.shapes.title.text = title
        body = slide.placeholders[1].text_frame
        body.text = bullets[0]
        for bullet in bullets[1:]:
            body.add_paragraph().text = bullet
        if notes:
            slide.notes_slide.notes_text_frame.text = notes
    presentation.save(path)


def write_txt(path: Path) -> None:
    path.write_text(FAQ_TEXT, encoding="utf-8")


def write_csv(path: Path) -> None:
    path.write_text("\n".join(",".join(r) for r in INVENTORY_ROWS) + "\n", encoding="utf-8")


WRITERS = {
    "employee_handbook.pdf": write_pdf,
    "atlas_x2_specification.docx": write_docx,
    "q3_sales_report.xlsx": write_xlsx,
    "onboarding_presentation.pptx": write_pptx,
    "support_faq.txt": write_txt,
    "inventory.csv": write_csv,
}


def generate(output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for name, writer in WRITERS.items():
        path = output_dir / name
        writer(path)
        paths[name] = path
    return paths


def write_questions(output_dir: Path) -> None:
    lines = ["# Example questions", "", "| Question | Expected source | Expected fact |", "|---|---|---|"]
    lines += [f"| {q} | `{src}` | {fact} |" for q, src, fact in EXAMPLE_QUESTIONS]
    lines += ["", "## Questions the documents cannot answer", "",
              "The assistant should reply that the documents do not contain sufficient information:", ""]
    lines += [f"- {q}" for q in UNANSWERABLE_QUESTIONS]
    (output_dir / "QUESTIONS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2] / "samples"
    for p in generate(target).values():
        print(f"wrote {p}")
    write_questions(target)
    print(f"wrote {target / 'QUESTIONS.md'}")
