from decimal import Decimal
from types import SimpleNamespace

from src.guidance import compare, extract_guidance, next_period, parse_sentence

PAGE = SimpleNamespace(page_content=(
    "For Q3, we expect revenue to be $44.0 billion, plus or minus 2%. "
    "We expect total revenue between $39.5 billion and $41.8 billion. "
    "GAAP and non-GAAP gross margins are expected to be 71.0% and 71.5%, plus or minus 50 basis points. "
    "We expect capital expenditures to be roughly $20 billion. Revenue was $35.1 billion last quarter."),
    metadata={"page": 7, "source": "nvda.pdf", "period": "Q2-2026"})


def test_parse():
    assert parse_sentence("We expect revenue to be $44.0 billion, plus or minus 2%.") == \
        ("revenue", Decimal("43120.00"), Decimal("44880.00"), "USD million")
    assert parse_sentence("Revenue was $35.1 billion last quarter.") is None  # no guidance cue


def test_extract_and_compare():
    g = extract_guidance([PAGE])
    assert {x.metric for x in g} == {"revenue", "gross_margin", "capex"} and all(x.page == 7 for x in g)
    facts = [{"metric": "revenue", "value": 46.7, "unit": "USD billion", "basis": "GAAP", "scope": "consolidated",
              "evidence": {"quote": "Revenue was $46.7 billion", "page": 3, "source": "nvda.pdf"}}]
    rows = compare(g, facts)
    rev = [r for r in rows if r["metric"] == "revenue"]
    assert rev[0]["verdict"] == "beat" and any(r["verdict"] == "no_actual" for r in rows)


def test_next_period():
    ps = ["Q4-2025", "Q1-2026", "Q2-2026"]
    assert next_period(ps, "Q4-2025") == "Q1-2026" and next_period(ps, "Q2-2026") is None


def test_endpoints(monkeypatch):
    from fastapi.testclient import TestClient
    from src import api
    monkeypatch.setattr(api, "service", lambda: SimpleNamespace(guidance_vs_actual=lambda c, p: {"company": c, "guided_in": p, "guidance": []}))
    c = TestClient(api.app)
    assert c.get("/guidance?company=meta&period=Q1-2025").json()["guided_in"] == "Q1-2025"
    assert c.get("/guidance?company=x&period=Q1-2025").status_code == 422
    assert "stages" in c.get("/observability/summary").json()
    assert c.get("/observability/prometheus").status_code == 200
