import re
from pathlib import Path

import fitz
from langchain_core.documents import Document

DATA_DIR = Path("data")

FILENAME_PATTERN = re.compile(
    r"^(?P<company>[A-Za-z]+)-(?P<quarter>Q[1-4])-(?P<year>\d{4})",
    re.IGNORECASE,
)


def parse_filename(stem: str) -> dict[str, str]:
    match = FILENAME_PATTERN.match(stem)
    if not match:
        return {
            "company": "unknown",
            "quarter": "unknown",
            "year": "unknown",
            "period": "unknown",
        }

    company = match.group("company").lower()
    quarter = match.group("quarter").upper()
    year = match.group("year")

    return {
        "company": company,
        "quarter": quarter,
        "year": year,
        "period": f"{quarter}-{year}",
    }


def extract_pdf_text(pdf_path: Path) -> str:
    with fitz.open(pdf_path) as doc:
        return "".join(page.get_text() for page in doc)


def load_documents(data_dir: Path | None = None) -> list[Document]:
    root = data_dir or DATA_DIR
    docs: list[Document] = []

    for pdf_file in sorted(root.glob("*.pdf")):
        text = extract_pdf_text(pdf_file)
        meta = parse_filename(pdf_file.stem)

        docs.append(
            Document(
                page_content=text,
                metadata={
                    "source": pdf_file.name,
                    **meta,
                },
            )
        )

    return docs
