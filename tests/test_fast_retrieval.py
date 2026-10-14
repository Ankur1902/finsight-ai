from types import SimpleNamespace
from langchain_core.documents import Document

from src.lexical_retriever import LexicalRetriever
from src.query_planner import Target
from src.guardrails import check_retrieval
from src.answer_cache import AnswerCache


def doc(text, quarter="Q1", year="2025"):
    return Document(page_content=text, metadata={"source": "microsoft.pdf", "page": 1,
        "company": "microsoft", "quarter": quarter, "year": year})


def retriever(pages):
    return LexicalRetriever(SimpleNamespace(fingerprint="test", pages=pages))


def test_financial_scoping_and_total_revenue_priority():
    r = retriever([doc("Segment revenue was $13.2 billion."),
        doc("Total company revenue was $65.6 billion."),
        doc("Total company revenue was $99 billion.", quarter="Q2")])
    result = r.retrieve_target("What was Microsoft's total revenue in FY25 Q1?", Target("microsoft", "Q1", "2025"), 2)
    assert "$65.6" in result[0].page_content
    assert all(d.metadata["quarter"] == "Q1" for d in result)
    assert all("rerank_score" not in d.metadata for d in result)
    assert check_retrieval(result).allowed


def test_growth_and_cloud_queries_match_reported_language():
    r = retriever([doc("Microsoft Cloud revenue was $38.9 billion and grew 22%."),
                   doc("Azure revenue increased with demand.")])
    result = r.retrieve_target("What was Microsoft Cloud revenue and how much did it grow?", Target("microsoft", "Q1", "2025"), 2)
    assert "$38.9" in result[0].page_content
    assert r.retrieve_target("Quantum computing export ban", Target("microsoft", "Q1", "2025"), 2) == []


def test_actual_company_revenue_precedes_frequent_segment_mentions():
    r = retriever([doc("Revenue was $65.6 billion for the quarter."),
        doc("Segment revenue and cloud revenue increased. " * 20),
        doc("Family of Apps revenue was $41.9 billion. Revenue increased.")])
    result = r.retrieve_target("Microsoft revenue FY25 Q1?", Target("microsoft", "Q1", "2025"), 2)
    assert "$65.6" in result[0].page_content


def test_cache_rejects_failed_answers_and_returns_copies(monkeypatch):
    cache = AnswerCache(capacity=1, ttl=10)
    now = [0]
    monkeypatch.setattr("src.answer_cache.monotonic", lambda: now[0])
    response = SimpleNamespace(blocked=False, flags=[], details={}, answer="Revenue [1].")
    cache.put("a", response)
    cache.get("a").details["mutated"] = True
    assert cache.get("a").details == {}
    cache.put("b", SimpleNamespace(blocked=True, flags=[], details={}))
    assert cache.get("b") is None
    cache.put("c", response)
    assert cache.get("a") is None
    now[0] = 11
    assert cache.get("c") is None


def test_corpus_snapshot_reuses_pages_and_detects_edits(monkeypatch, tmp_path):
    from src.corpus import get_corpus
    file = tmp_path / "microsoft.pdf"
    file.write_text("First version")
    calls = []
    def load(directory):
        calls.append(directory)
        return [doc(file.read_text())]
    monkeypatch.setattr("src.corpus.load_documents", load)
    first = get_corpus(tmp_path)
    assert get_corpus(tmp_path) is first and len(calls) == 1
    file.write_text("Changed source version")
    assert get_corpus(tmp_path).fingerprint != first.fingerprint
    assert len(calls) == 2


def test_cache_configuration_rejects_invalid_bounds():
    import pytest
    for capacity, ttl in [(0, 10), (-1, 10), (True, 10), (1, 0), (1, float("nan"))]:
        with pytest.raises(ValueError):
            AnswerCache(capacity=capacity, ttl=ttl)


def test_corpus_does_not_publish_a_mixed_update(monkeypatch, tmp_path):
    import pytest
    from src.corpus import get_corpus
    file = tmp_path / "changing.pdf"
    file.write_text("start")
    def load(_directory):
        content = file.read_text()
        file.write_text(content + " updated")
        return [doc(content)]
    monkeypatch.setattr("src.corpus.load_documents", load)
    with pytest.raises(RuntimeError, match="changed during loading"):
        get_corpus(tmp_path)
