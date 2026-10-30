"""Keyless demo backend. Runs the REAL pipeline (lexical retrieval over the PDFs,
guardrails, claim verification, calculator tool, observability, security
middleware). Only the language model is replaced by a deterministic extractive
stand-in that quotes retrieved passages, so no API key is needed.

    FINSIGHT_RETRIEVAL_MODE=lexical python -m uvicorn demo.demo_server:app --port 8000

NOT for production: the stand-in is not an AI model."""
import json
import os
import re

os.environ.setdefault("FINSIGHT_RETRIEVAL_MODE", "lexical")
os.environ.setdefault("FINSIGHT_SEMANTIC_CACHE", "1")

import src.api as api
import src.rag as rag
from src.agent import PLAN_SYSTEM
from src.calculator import numbers_in
import tests.e2e_fixture_api as fixture  # deterministic metric extraction from the real PDFs
from tests.e2e_fixture_api import FixtureModel

api.answer_chat = fixture.original_chat  # the fixture module stubs chat; use the real pipeline

_SOURCE = re.compile(r'<source id="(\d+)"([^>]*)>\n(.*?)\n</source>', re.S)
_STOP = {"what", "was", "the", "did", "how", "much", "and", "for", "from", "meta", "microsoft", "nvidia", "in", "of", "to", "a", "is"}


def _sources(user):
    return {int(i): t for i, _attrs, t in _SOURCE.findall(user)}


def _periods(user):
    """source id -> (fiscal year, quarter) from the prompt's fiscal_period attribute."""
    out = {}
    for i, attrs, _t in _SOURCE.findall(user):
        m = re.search(r'fiscal_period="Q(\d) FY(\d{4})"', attrs)
        if m:
            out[int(i)] = (int(m.group(2)), int(m.group(1)))
    return out


def _question(user):
    return user.rsplit("Question:", 1)[-1].strip()


def _revenue(text):
    m = re.search(r"total revenue was \$(\d+(?:\.\d+)?) billion", text)
    return m.group(1) if m else None


class DemoModel(FixtureModel):
    name = "demo-extractive:no-api-key"

    def generate(self, system, user, max_tokens=None):
        if user.lstrip().startswith("{") and "<sources>" not in user:
            return super().generate(system, user, max_tokens)  # analytics extraction
        sources = _sources(user)
        if system == PLAN_SYSTEM:
            when = _periods(user)
            vals = sorted(((i, _revenue(t)) for i, t in sources.items() if _revenue(t) and i in when),
                          key=lambda v: when[v[0]])  # chronological, not retrieval order
            years = [when[i][0] for i, _ in vals]
            vals = [v for v, y in zip(vals, years) if y == years[0]][:2]  # same fiscal year
            if len(vals) >= 2 and re.search(r"grow|change|increase|differ", _question(user), re.I):
                (ia, a), (ib, b) = vals[0], vals[-1]
                return json.dumps({"calculations": [{"op": "pct_change", "a": a, "a_source": ia, "b": b,
                                                     "b_source": ib, "label": "Revenue growth"}]})
            return json.dumps({"calculations": []})
        q = _question(user)
        if user.startswith("<calculations>"):
            m = re.search(r"- Revenue growth: .*= ([\d.\-]+)%", user)
            ids = re.search(r"sources \[(\d+), (\d+)\]", user)
            cite = f" [{ids.group(1)}, {ids.group(2)}]" if ids else ""
            parts = [f"Revenue grew {m.group(1)}% between the two quarters (computed exactly by the calculator tool){cite}."] if m else []
            used = set(re.findall(r"sources \[(\d+), (\d+)\]", user)[0]) if re.search(r"sources \[\d+, \d+\]", user) else set()
            for i, t in sorted(sources.items()):
                if _revenue(t) and (not used or str(i) in used):
                    s = re.search(r"[^.\n]*total revenue was \$[\d.]+ billion[^.\n]*\.?", t).group(0).strip()
                    parts.append(f"{s} [{i}]")
            return " ".join(parts)
        terms = {w for w in re.findall(r"[a-z]{3,}", q.lower())} - _STOP
        best, best_score = None, 0
        for i, t in sorted(sources.items()):
            for s in re.split(r"(?<=[.!?])\s+", t.replace("\n", " ")):
                if re.search(r"\d", s) and len(s) < 400:
                    score = len(terms & set(re.findall(r"[a-z]{3,}", s.lower()))) + (2 if "total revenue" in s and "revenue" in terms else 0)
                    if score > best_score:
                        best, best_score = (i, s.strip()), score
        if not best:
            return "I couldn't find that information in the provided documents."
        return f"{best[1]} [{best[0]}]"


_model = DemoModel()
rag.get_llm = lambda: _model
import src.llm as llm_module
llm_module.get_llm = lambda: _model
app = api.app
