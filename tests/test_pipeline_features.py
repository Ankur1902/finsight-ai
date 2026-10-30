import json
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document

from src import rag
from src.errors import GenerationError
from src.lexical_retriever import LexicalRetriever
from src.observability import METRICS, estimate_cost
from src.router import RoutedLLM, classify
from src.semantic_cache import SemanticCache


def doc(text, quarter, page):
    return Document(page_content=text, metadata={"source": "m.pdf", "page": page, "company": "microsoft",
                    "company_name": "Microsoft", "quarter": quarter, "year": "2025", "period": f"{quarter}-2025"})


@pytest.fixture
def retriever():
    pages = [doc("Microsoft total revenue was $65.6 billion in the quarter.", "Q1", 1),
             doc("Microsoft total revenue was $69.6 billion in the quarter.", "Q2", 2)]
    return LexicalRetriever(SimpleNamespace(fingerprint="t", pages=pages))


class FakeLLM:
    name = "fake:m"

    def __init__(self, replies):
        self.replies, self.calls = list(replies), 0

    def generate(self, system, user, max_tokens=None):
        self.calls += 1
        return self.replies.pop(0)


def run(monkeypatch, retriever, llm, **kw):
    monkeypatch.setattr(rag, "get_llm", lambda: llm)
    rag.ANSWERS.clear()
    return rag.answer_question("What was Microsoft total revenue in Q1 2025?", retriever=retriever, **kw)


def test_claims_attached(monkeypatch, retriever):
    r = run(monkeypatch, retriever, FakeLLM(["Microsoft total revenue was $65.6 billion in the quarter [1]."]))
    assert not r.blocked and r.details["claim_summary"]["supported"] == 1


def test_agentic_calculator_numbers_allowed(monkeypatch, retriever):
    plan = json.dumps({"calculations": [{"op": "pct_change", "a": "65.6", "a_source": 1, "b": "69.6", "b_source": 1,
                                         "label": "growth"}]})
    # Operand 69.6 is not in source 1 -> rejected; the answer's computed figure must then fail grounding.
    llm = FakeLLM([plan, "Revenue grew 6.10% [1]."])
    r = run(monkeypatch, retriever, llm, tools=True)
    assert r.details["calculations"] == [] and r.blocked

    good = json.dumps({"calculations": [{"op": "difference", "a": "65.6", "a_source": 1, "b": "65.6", "b_source": 1}]})
    llm = FakeLLM([good, "Revenue was $65.6 billion [1], a computed difference of 0.00 [1]."])
    r = run(monkeypatch, retriever, llm, tools=True)
    assert r.details["calculations"][0]["result"] == "0.00" and not r.blocked


def test_router_classifies_and_escalates():
    assert classify("What was Microsoft's revenue in Q1 2025?") == "simple"
    assert classify("Compare Microsoft and Meta capex across quarters") == "complex"
    cheap, strong = FakeLLM(["a"]), FakeLLM(["b"])
    router = RoutedLLM(cheap, strong)
    assert router.generate("s", "Question: revenue in Q1 2025?") == "a" and router.last_route == "cheap"
    assert router.generate("s", "Question: why did margins change?") == "b" and router.last_route == "strong"

    def boom(*a, **k):
        raise GenerationError("x")
    cheap.generate = boom
    strong.replies = ["c"]
    assert router.generate("s", "Question: revenue in Q1 2025?") == "c" and router.last_route == "escalated"


def test_semantic_cache_paraphrase_and_safety():
    c = SemanticCache(threshold=0.8)
    resp = SimpleNamespace(blocked=False, flags=[], details={}, answer="x")
    c.put("scope", "What was Microsoft total revenue in Q1 2025?", resp)
    assert c.get("scope", "What was Microsoft's total revenue in Q1 2025?") is not None
    assert c.get("scope", "What was Microsoft total revenue in Q2 2025?") is None  # number differs
    assert c.get("other", "What was Microsoft total revenue in Q1 2025?") is None  # scope differs
    c.put("s2", "Did margins grow in Q1 2025?", resp)
    assert c.get("s2", "Did margins fall in Q1 2025?") is None  # direction flips


def test_semantic_cache_in_pipeline(monkeypatch, retriever):
    monkeypatch.setenv("FINSIGHT_SEMANTIC_CACHE", "1")
    rag.SEMANTIC.clear()
    llm = FakeLLM(["Microsoft total revenue was $65.6 billion in the quarter [1]."])
    monkeypatch.setattr(rag, "get_llm", lambda: llm)
    rag.ANSWERS.clear()
    rag.answer_question("What was Microsoft total revenue in Q1 2025?", retriever=retriever)
    second = rag.answer_question("What was Microsoft's total revenue in Q1 2025??", retriever=retriever)
    assert llm.calls == 1 and second.details.get("cached")
    rag.SEMANTIC.clear()


def test_metrics_cost():
    assert estimate_cost("gemini:gemini-3.1-flash-lite", 1_000_000, 0) == pytest.approx(0.10)
    METRICS.record_request(route="cheap", model="gemini:gemini-3.1-flash-lite", tokens_in=1000, tokens_out=100, correct=True)
    assert METRICS.summary()["routes"]["cheap"]["cost_per_correct_answer_usd"] is not None
    assert "finsight_requests_total" in METRICS.prometheus()
