"""PDF loading with metadata parsed from the transcript itself.

Filenames are unreliable (e.g. `Microsoft-Q1-2026-...pdf` actually contains the
FY26 *third* quarter call), so company / fiscal period / call date are read from
the transcript header and the filename is only a fallback.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import fitz
from langchain_core.documents import Document

from .config import DATA_DIR

COMPANY_NAMES = {
    "meta": "Meta Platforms",
    "microsoft": "Microsoft",
    "nvda": "NVIDIA",
}

_ORDINALS = {"first": "Q1", "second": "Q2", "third": "Q3", "fourth": "Q4"}

FILENAME_PATTERN = re.compile(
    r"^(?P<company>[A-Za-z]+)-(?P<quarter>Q[1-4])-(?P<year>\d{4})",
    re.IGNORECASE,
)

_MONTH = (
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
)
_DATE_PATTERNS = [
    # "October 30, 2024" / "April 30th, 2025"
    (re.compile(rf"\b({_MONTH})\s+(\d{{1,2}})(?:st|nd|rd|th)?,\s+(20\d\d)"), "mdy"),
    # "28-May-2025"
    (re.compile(rf"\b(\d{{1,2}})-({_MONTH})-(20\d\d)"), "dmy"),
]


def _detect_company(header: str) -> str | None:
    h = header.lower()
    if "nvidia" in h or "(nvda)" in h:
        return "nvda"
    if "meta platforms" in h or "(meta)" in h:
        return "meta"
    if "microsoft" in h:
        return "microsoft"
    return None


def _detect_period(header: str) -> tuple[str | None, str | None]:
    # Microsoft: "Microsoft FY25 First Quarter Earnings Conference Call"
    m = re.search(r"FY(\d{2})\s+(First|Second|Third|Fourth)\s+Quarter", header, re.I)
    if m:
        return _ORDINALS[m.group(2).lower()], f"20{m.group(1)}"
    # Meta: "First Quarter 2025 Results Conference Call"
    m = re.search(r"(First|Second|Third|Fourth)\s+Quarter\s+(20\d\d)", header, re.I)
    if m:
        return _ORDINALS[m.group(1).lower()], m.group(2)
    # NVIDIA (FactSet): "Q1 2026 Earnings Call"
    m = re.search(r"\bQ([1-4])\s+(20\d\d)\s+Earnings\s+Call", header, re.I)
    if m:
        return f"Q{m.group(1)}", m.group(2)
    return None, None


def _detect_call_date(header: str) -> str | None:
    for pattern, order in _DATE_PATTERNS:
        m = pattern.search(header)
        if not m:
            continue
        if order == "mdy":
            month, day, year = m.groups()
        else:
            day, month, year = m.groups()
        try:
            return datetime.strptime(f"{month[:3]} {day} {year}", "%b %d %Y").date().isoformat()
        except ValueError:
            continue
    return None


def parse_filename(stem: str) -> dict[str, str]:
    match = FILENAME_PATTERN.match(stem)
    if not match:
        return {"company": "unknown", "quarter": "unknown", "year": "unknown"}
    return {
        "company": match.group("company").lower(),
        "quarter": match.group("quarter").upper(),
        "year": match.group("year"),
    }


def parse_metadata(header: str, stem: str) -> dict[str, str]:
    """Fiscal period metadata; header wins over filename when both exist."""
    fallback = parse_filename(stem)
    company = _detect_company(header) or fallback["company"]
    quarter, year = _detect_period(header)
    quarter = quarter or fallback["quarter"]
    year = year or fallback["year"]

    return {
        "company": company,
        "company_name": COMPANY_NAMES.get(company, company),
        "quarter": quarter,
        "year": year,  # fiscal year, as the company labels it
        "period": f"{quarter}-{year}",
        "call_date": _detect_call_date(header) or "unknown",
    }


def _clean(text: str) -> str:
    text = text.replace("‐", "-").replace("’", "'").replace("�", "'")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def load_documents(data_dir: Path | None = None) -> list[Document]:
    """One Document per PDF page, so citations can point at a page."""
    root = data_dir or DATA_DIR
    docs: list[Document] = []

    for pdf_file in sorted(root.glob("*.pdf")):
        with fitz.open(pdf_file) as pdf:
            pages = [page.get_text() for page in pdf]

        header = " ".join(pages[:2])[:3000]
        meta = parse_metadata(header, pdf_file.stem)

        for page_number, page_text in enumerate(pages, start=1):
            text = _clean(page_text)
            if len(text) < 40:
                continue
            docs.append(
                Document(
                    page_content=text,
                    metadata={"source": pdf_file.name, "page": page_number, **meta},
                )
            )

    return docs
