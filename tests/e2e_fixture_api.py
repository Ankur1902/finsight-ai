"""Loopback-only browser test harness. NEVER use this application in production.

Replaces model output with labeled deterministic fixtures, while exercising the
real analytics validation, comparison math, HTTP routes, PDFs and feedback store.
This verifies UI integration, not model quality or vector retrieval.
Run: python -m uvicorn tests.e2e_fixture_api:app --host 127.0.0.1 --port 18001
"""
import json
import re
from pathlib import Path

import src.api as api
from src.analytics import AnalyticsService
from src.chat import ChatAnswer, ChatPlan, ChatSource, ChatTarget
from src.config import ROOT_DIR
from src.ingest import load_documents

pages = load_documents()
facts = {}
for period in ("Q1-2025", "Q2-2025"):
    for page in pages:
        if page.metadata["company"] != "meta" or page.metadata["period"] != period:
            continue
        for metric, pattern in (
            ("revenue", r"Q[12] total revenue was \$(\d+\.\d+) billion[^\n]*"),
            ("capex", r"Capital expenditures, including principal payments on finance leases, were \$(\d+\.\d+) billion[^\n]*"),
        ):
            match = re.search(pattern, page.page_content)
            if match:
                facts[(period, metric)] = {
                    "metric": metric, "value": float(match[1]), "unit": "USD billion",
                    "basis": "unspecified", "scope": "consolidated",
                    "evidence": {"source": page.metadata["source"], "page": page.metadata["page"], "quote": match[0].strip()},
                }
assert len(facts) == 4, "Fixture quotes must exist in the actual corpus"


class FixtureModel:
    name = "test-fixture:deterministic-not-ai"

    def generate(self, system, user, max_tokens=None):
        payload = json.loads(user)
        if "metric" in payload:
            fact = facts.get((payload["reporting_period"], payload["metric"]))
            supported = fact and fact["evidence"]["source"] == payload["source"] and fact["evidence"]["page"] == payload["page"]
            return json.dumps({"facts": [fact] if supported else []})
        before = facts[(payload["before_period"], "revenue")]["evidence"]
        after = facts[(payload["after_period"], "revenue")]["evidence"]
        return json.dumps({"changes": [{"topic": "Reported revenue", "category": "business",
            "summary": "The later quarter reports higher total revenue. This is a deterministic UI test fixture.",
            "before": before, "after": after}]} if payload["topic"] == "Business drivers" else {"changes": []})


fixture_service = AnalyticsService(cache_path=ROOT_DIR / ".e2e" / "fixture-analytics.sqlite3", llm_factory=FixtureModel)
api.service = lambda: fixture_service
original_chat = api.answer_chat


def fixture_chat(body):
    # Keep actual input guardrails, including injection refusals.
    from src.guardrails import check_input
    if not check_input(body.question).allowed:
        return original_chat(body)
    period = "Q2-2025" if "q2" in body.question.lower() else "Q1-2025"
    fact = facts[(period, "revenue")]
    evidence = fact["evidence"]
    return ChatAnswer(model=FixtureModel.name, question=body.question,
        answer=f"**UI test fixture:** Meta's total revenue in {period} was ${fact['value']} billion [1].",
        sources=[ChatSource(id=1, source=evidence["source"], page=evidence["page"],
            company="meta", company_name="Meta", quarter=period[:2], year="2025", period=period,
            snippet=evidence["quote"], excerpt=evidence["quote"])],
        plan=ChatPlan(inherited=bool(body.history), targets=[ChatTarget(company="meta", quarter=period[:2], year="2025", label=f"Meta {period[:2]} FY2025")]),
        timings_ms={"generate": 0, "total": 0})


api.answer_chat = fixture_chat
app = api.app
