from src.chunking import split_documents
from src.ingest import load_documents, parse_metadata


def test_header_beats_misleading_filename():
    header = "Microsoft FY26 Third Quarter Earnings Conference Call\nWednesday April 29, 2026"
    meta = parse_metadata(header, "Microsoft-Q1-2026-Earnings Conference Call")
    assert (meta["company"], meta["quarter"], meta["year"], meta["call_date"]) == (
        "microsoft", "Q3", "2026", "2026-04-29"
    )


def test_meta_and_nvidia_headers():
    meta = parse_metadata("Meta Platforms, Inc. (META)\nFirst Quarter 2025 Results Conference Call\nApril 30th, 2025", "x")
    assert meta["period"] == "Q1-2025" and meta["call_date"] == "2025-04-30"
    nv = parse_metadata("28-May-2025\nNVIDIA Corp. (NVDA)\nQ1 2026 Earnings Call", "x")
    assert nv["company"] == "nvda" and nv["period"] == "Q1-2026" and nv["call_date"] == "2025-05-28"


def test_filename_fallback():
    meta = parse_metadata("no header here", "META-Q2-2025-Earnings")
    assert meta["company"] == "meta" and meta["period"] == "Q2-2025"


def test_real_corpus_pages_and_chunk_ids():
    docs = load_documents()
    assert all("page" in d.metadata for d in docs)
    chunks = split_documents(docs[:5])
    ids = [c.metadata["chunk_id"] for c in chunks]
    assert len(ids) == len(set(ids))
    assert chunks[0].page_content.startswith("[")  # contextual header
    assert split_documents(docs[:5])[0].metadata["chunk_id"] == ids[0]  # deterministic
