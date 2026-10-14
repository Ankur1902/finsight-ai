import json
from decimal import Decimal

import pytest
from langchain_core.documents import Document

from src.analytics import AnalyticsService, Evidence, MetricFact, metric_delta, parse_json, validate_fact


def page(text="Total revenue was $42.3 billion.", period="Q1-2025"):
    q, y = period.split("-")
    return Document(page_content=text, metadata={"source": "meta.pdf", "page": 1, "company": "meta", "company_name": "Meta", "quarter": q, "year": y, "period": period, "call_date": "2025-04-30"})


def fact(**kwargs):
    data = dict(metric="revenue", value=Decimal("42.3"), unit="USD billion", basis="unspecified", scope="consolidated", evidence=Evidence(source="meta.pdf", page=1, quote="Total revenue was $42.3 billion."))
    data.update(kwargs)
    return MetricFact(**data)


def test_exact_quote_value_and_unit_required():
    assert validate_fact(fact(), [page()])
    assert not validate_fact(fact(value=Decimal("47.5")), [page()])
    assert not validate_fact(fact(unit="USD million"), [page()])
    assert not validate_fact(fact(evidence=Evidence(source="meta.pdf", page=2, quote="Total revenue was $42.3 billion.")), [page()])


def test_outlook_is_not_actual():
    quote = "We expect total revenue of $42.3 billion."
    assert not validate_fact(fact(evidence=Evidence(source="meta.pdf", page=1, quote=quote)), [page(quote)])


def test_segment_revenue_not_consolidated():
    quote = "Data Center revenue was $42.3 billion."
    assert not validate_fact(fact(evidence=Evidence(source="meta.pdf", page=1, quote=quote)), [page(quote)])


def test_non_gaap_cannot_be_gaap():
    quote = "Non-GAAP total revenue was $42.3 billion."
    assert not validate_fact(fact(basis="GAAP", evidence=Evidence(source="meta.pdf", page=1, quote=quote)), [page(quote)])


def test_delta_and_zero_baseline():
    a = fact().model_dump(mode="json")
    b = dict(a, value=47.5)
    assert metric_delta(a, b)["absolute"] == 5.2
    assert metric_delta(dict(a, value=0), b)["relative_percent"] is None
    assert metric_delta(a, dict(b, basis="GAAP")) is None
    assert metric_delta(a, dict(b, unit="USD million")) is None


def test_margin_delta_is_percentage_points():
    a = fact(metric="gross_margin", unit="percent", value=Decimal("70")).model_dump(mode="json")
    assert metric_delta(a, dict(a, value=72))["unit"] == "percentage points"


def test_json_is_strict():
    assert parse_json('```json\n{"facts": []}\n```') == {"facts": []}
    with pytest.raises(ValueError):
        parse_json('Here is the answer: {"facts": []}')


@pytest.mark.parametrize("text", ['{"value": NaN}', '{"value": Infinity}', '{"facts": [], "facts": []}', '[]', 'null'])
def test_ambiguous_or_non_finite_json_is_rejected(text):
    with pytest.raises(ValueError):
        parse_json(text)


def test_basic_eps_cannot_be_presented_as_diluted():
    quote = "Earnings per share were $3.30."
    candidate = fact(metric="eps", value=Decimal("3.30"), unit="USD/share",
                     evidence=Evidence(source="meta.pdf", page=1, quote=quote))
    assert not validate_fact(candidate, [page(quote)])
    diluted = "Diluted earnings per share were $3.30."
    assert validate_fact(candidate.model_copy(update={"evidence": Evidence(source="meta.pdf", page=1, quote=diluted)}), [page(diluted)])


def test_cache_failure_preserves_analysis(tmp_path):
    cache = tmp_path / "not-a-database"
    cache.mkdir()
    llm = FakeLLM()
    service = AnalyticsService(cache_path=cache, llm_factory=lambda: llm)
    service._pages = lambda: [page()]
    assert service.metrics("meta", "Q1-2025")["facts"][0]["value"] == 42.3


def test_corrupted_cache_row_is_recomputed(tmp_path):
    import sqlite3
    llm = FakeLLM()
    cache = tmp_path / "cache.sqlite"
    service = AnalyticsService(cache_path=cache, llm_factory=lambda: llm)
    service._pages = lambda: [page()]
    service.metrics("meta", "Q1-2025")
    with sqlite3.connect(cache) as db:
        db.execute("UPDATE results SET payload='[]'")
    assert service.metrics("meta", "Q1-2025")["facts"][0]["value"] == 42.3
    assert llm.calls == 2


class FakeLLM:
    name = "test-model"
    calls = 0

    def generate(self, system, user, max_tokens=None):
        self.calls += 1
        payload = json.loads(user)
        if "metric" not in payload:
            return '{"changes": []}'
        return json.dumps({"facts": [fact().model_dump(mode="json")]})


def test_cache_invalidates_on_transcript_change(tmp_path):
    llm = FakeLLM()
    service = AnalyticsService(cache_path=tmp_path / "cache.sqlite", llm_factory=lambda: llm)
    pages = [page()]
    service._pages = lambda: pages
    result = service.metrics("meta", "Q1-2025")
    assert len(result["facts"]) == 1
    service.metrics("meta", "Q1-2025")
    assert llm.calls == 1
    pages[0] = page("Total revenue was $42.3 billion. More commentary.")
    service.metrics("meta", "Q1-2025")
    assert llm.calls == 2


def test_conflicts_withheld(tmp_path):
    class ConflictingLLM(FakeLLM):
        def generate(self, system, user, max_tokens=None):
            return json.dumps({"facts": [fact().model_dump(mode="json"), fact(value=Decimal("47.5"), evidence=Evidence(source="meta.pdf", page=1, quote="Total revenue was $47.5 billion.")).model_dump(mode="json")]})
    service = AnalyticsService(cache_path=tmp_path / "cache.sqlite", llm_factory=ConflictingLLM)
    service._pages = lambda: [page("Total revenue was $42.3 billion. Total revenue was $47.5 billion.")]
    result = service.metrics("meta", "Q1-2025")
    assert not result["facts"] and len(result["conflicts"]) == 1


def test_failed_extraction_not_cached(tmp_path):
    class BrokenLLM(FakeLLM):
        def generate(self, system, user, max_tokens=None):
            self.calls += 1
            return "not JSON"
    llm = BrokenLLM()
    service = AnalyticsService(cache_path=tmp_path / "cache.sqlite", llm_factory=lambda: llm)
    service._pages = lambda: [page()]
    assert service.metrics("meta", "Q1-2025")["failed_extractions"] == 1
    service.metrics("meta", "Q1-2025")
    assert llm.calls == 2


def test_missing_and_reversed_periods(tmp_path):
    service = AnalyticsService(cache_path=tmp_path / "cache.sqlite")
    service._pages = lambda: [page(), page(period="Q2-2025")]
    with pytest.raises(ValueError):
        service.metrics("meta", "Q3-2025")
    with pytest.raises(ValueError):
        service.changes("meta", "Q2-2025", "Q1-2025")


def test_narrative_requires_both_period_quotes(tmp_path):
    class NarrativeLLM(FakeLLM):
        def generate(self, system, user, max_tokens=None):
            payload = json.loads(user)
            if "metric" in payload:
                return '{"facts": []}'
            return json.dumps({"changes": [{"topic": "AI spending", "category": "investment", "summary": "Management discussed AI investment in both periods.", "before": {"source": "meta.pdf", "page": 1, "quote": "AI investment supported demand."}, "after": {"source": "meta.pdf", "page": 1, "quote": "A quotation absent from the new call."}}]})
    service = AnalyticsService(cache_path=tmp_path / "cache.sqlite", llm_factory=NarrativeLLM)
    service._pages = lambda: [page("AI investment supported demand.", "Q1-2025"), page("AI investment increased with demand.", "Q2-2025")]
    assert service.changes("meta", "Q1-2025", "Q2-2025")["changes"] == []


def test_narrative_with_supported_quotes_is_returned(tmp_path):
    class NarrativeLLM(FakeLLM):
        def generate(self, system, user, max_tokens=None):
            payload = json.loads(user)
            if "metric" in payload:
                return '{"facts": []}'
            return json.dumps({"changes": [{"topic": "AI spending", "category": "investment", "summary": "The later call describes increased AI investment.", "before": {"source": "meta.pdf", "page": 1, "quote": "AI investment supported demand."}, "after": {"source": "meta.pdf", "page": 1, "quote": "AI investment increased with demand."}}]})
    service = AnalyticsService(cache_path=tmp_path / "cache.sqlite", llm_factory=NarrativeLLM)
    service._pages = lambda: [page("AI investment supported demand.", "Q1-2025"), page("AI investment increased with demand.", "Q2-2025")]
    assert service.changes("meta", "Q1-2025", "Q2-2025")["changes"]


def test_explicit_other_period_and_annual_results_rejected():
    for quote in ["Q2 2025 total revenue was $42.3 billion.", "Full-year total revenue was $42.3 billion."]:
        evidence = Evidence(source="meta.pdf", page=1, quote=quote)
        assert not validate_fact(fact(evidence=evidence), [page(quote)])



def test_negative_baseline_does_not_report_a_misleading_growth_rate():
    before = fact(metric="eps", unit="USD/share", value=Decimal("-1")).model_dump(mode="json")
    after = dict(before, value=2)
    assert metric_delta(before, after)["absolute"] == 3
    assert metric_delta(before, after)["relative_percent"] is None



def test_default_cache_path_honors_environment_without_loading_model(monkeypatch, tmp_path):
    path = tmp_path / "analytics.sqlite3"
    monkeypatch.setenv("FINSIGHT_ANALYTICS_CACHE", str(path))
    assert AnalyticsService().cache_path == path


def test_structured_period_extraction_is_one_call_and_validated(tmp_path):
    class StructuredModel:
        name = "structured-test"
        calls = 0
        def generate_json(self, system, user, schema, max_tokens=None):
            self.calls += 1
            return json.dumps({"facts": [fact().model_dump(mode="json"),
                fact(value=Decimal("99")).model_dump(mode="json")]})
    model = StructuredModel()
    service = AnalyticsService(cache_path=tmp_path / "cache.sqlite", llm_factory=lambda: model)
    service._pages = lambda: [page(), page("Some other revenue commentary.")]
    result = service.metrics("meta", "Q1-2025")
    assert model.calls == 1 and len(result["facts"]) == 1
    assert result["facts"][0]["value"] == 42.3 and result["rejected_facts"] == 1


def test_segment_margin_cannot_be_company_margin():
    quote = "Family of Apps operating margin was 52%."
    candidate = fact(metric="operating_margin", value=Decimal("52"), unit="percent",
        evidence=Evidence(source="meta.pdf", page=1, quote=quote))
    assert not validate_fact(candidate, [page(quote)])


def test_cached_metrics_do_not_wait_for_unrelated_generation(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    started, release = Event(), Event()
    class WaitingModel(FakeLLM):
        def generate(self, system, user, max_tokens=None):
            if json.loads(user)["reporting_period"] == "Q2-2025":
                started.set()
                assert release.wait(5)
                return '{"facts": []}'
            return super().generate(system, user, max_tokens)
    model = WaitingModel()
    service = AnalyticsService(cache_path=tmp_path / "cache.sqlite", llm_factory=lambda: model)
    service._pages = lambda: [page(), page(period="Q2-2025")]
    service.metrics("meta", "Q1-2025")
    with ThreadPoolExecutor(max_workers=2) as pool:
        slow = pool.submit(service.metrics, "meta", "Q2-2025")
        try:
            assert started.wait(2)
            cached = pool.submit(service.metrics, "meta", "Q1-2025")
            assert cached.result(timeout=1)["facts"][0]["value"] == 42.3
        finally:
            release.set()
        slow.result(timeout=3)
