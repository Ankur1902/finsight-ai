"""Deterministic (no-LLM-judge) evaluation of retrieval, generation and guardrails."""

from __future__ import annotations

import re
import statistics
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from src.guardrails import REFUSAL_TEXT

COMPANY_ALIASES = {"nvidia": "nvda", "nvda": "nvda", "meta": "meta", "microsoft": "microsoft", "msft": "microsoft"}
ANSWERABLE = {"factoid", "comparison"}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _company(name: str | None) -> str | None:
    return COMPANY_ALIASES.get((name or "").lower(), name)


def expected_targets(case: dict[str, Any]) -> list[tuple[str | None, str | None, str | None]]:
    if case.get("expected_targets"):
        return [(_company(c), q, y) for c, q, y in case["expected_targets"]]
    if case.get("expected_company") or case.get("expected_quarter") or case.get("expected_year"):
        return [(_company(case.get("expected_company")), case.get("expected_quarter"), case.get("expected_year"))]
    return []


def _matches(meta: dict[str, Any], target: tuple) -> bool:
    company, quarter, year = target
    if company and _company(meta.get("company")) != company:
        return False
    if quarter and str(meta.get("quarter", "")).upper() != quarter.upper():
        return False
    if year and str(meta.get("year", "")) != str(year):
        return False
    return True


def relevance_flags(metas: list[dict], case: dict) -> list[bool]:
    targets = expected_targets(case)
    return [any(_matches(m, t) for t in targets) for m in metas] if targets else []


def target_coverage(metas: list[dict], case: dict) -> float | None:
    targets = expected_targets(case)
    if not targets:
        return None
    return sum(any(_matches(m, t) for m in metas) for t in targets) / len(targets)


def keyword_recall(text: str, keywords: list[str]) -> float | None:
    if not keywords:
        return None
    normalized = _normalize(text)
    return sum(kw.lower() in normalized for kw in keywords) / len(keywords)


def hit_at_k(flags: list[bool]) -> float:
    return 1.0 if any(flags) else 0.0


def mrr(flags: list[bool]) -> float:
    return next((1.0 / i for i, f in enumerate(flags, start=1) if f), 0.0)


def precision_at_k(flags: list[bool]) -> float:
    return sum(flags) / len(flags) if flags else 0.0


def answer_term_match(answer: str, terms: list[str], require_all: bool) -> float | None:
    if not terms:
        return None
    normalized = _normalize(answer)
    hits = [_normalize(t) in normalized for t in terms]
    return float(all(hits)) if require_all else float(any(hits))


def refused(answer: str, blocked: bool) -> bool:
    return blocked or _normalize(REFUSAL_TEXT).rstrip(".") in _normalize(answer)


def _mean(values: list[float | None]) -> float | None:
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    return values[min(len(values) - 1, int(round(q * (len(values) - 1))))]


@dataclass
class CaseResult:
    id: str
    category: str
    question: str
    hit_at_k: float | None = None
    mrr: float | None = None
    precision_at_k: float | None = None
    target_coverage: float | None = None
    keyword_recall_at_k: float | None = None
    retrieved_sources: list[str] = field(default_factory=list)
    answer_term_match: float | None = None
    refusal_correct: float | None = None
    flag_correct: float | None = None
    citation_count: int | None = None
    numeric_grounding: float | None = None
    flags: list[str] = field(default_factory=list)
    latency_ms: float | None = None
    answer: str | None = None
    contexts: list[str] = field(default_factory=list)


@dataclass
class EvalReport:
    mode: str
    num_cases: int
    summary: dict[str, float | None]
    cases: list[CaseResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"mode": self.mode, "num_cases": self.num_cases, "summary": self.summary,
                "cases": [asdict(c) for c in self.cases]}


def _score_retrieval(result: CaseResult, metas: list[dict], contexts: list[str], case: dict) -> None:
    flags = relevance_flags(metas, case)
    if flags:
        result.hit_at_k = hit_at_k(flags)
        result.mrr = mrr(flags)
        result.precision_at_k = precision_at_k(flags)
        result.target_coverage = target_coverage(metas, case)
    result.keyword_recall_at_k = keyword_recall("\n".join(contexts), case.get("expected_keywords", []))
    result.retrieved_sources = [f"{m.get('source')}#p{m.get('page')}" for m in metas]


def evaluate_retrieval(retriever, cases: list[dict[str, Any]]) -> EvalReport:
    results = []
    for case in cases:
        category = case.get("category", "factoid")
        result = CaseResult(case["id"], category, case["question"])
        if category in ANSWERABLE:
            docs = retriever.retrieve(case["question"])
            _score_retrieval(result, [d.metadata for d in docs], [d.page_content for d in docs], case)
        results.append(result)

    scored = [r for r in results if r.hit_at_k is not None]
    return EvalReport(
        mode="retrieval",
        num_cases=len(scored),
        summary={
            "hit_at_k": _mean([r.hit_at_k for r in scored]),
            "mrr": _mean([r.mrr for r in scored]),
            "precision_at_k": _mean([r.precision_at_k for r in scored]),
            "target_coverage": _mean([r.target_coverage for r in scored]),
            "keyword_recall_at_k": _mean([r.keyword_recall_at_k for r in scored]),
        },
        cases=results,
    )


def evaluate_rag(answer_fn: Callable, cases: list[dict[str, Any]]) -> EvalReport:
    """answer_fn(question) -> RAGResponse (see src.rag.answer_question)."""
    results = []
    for case in cases:
        category = case.get("category", "factoid")
        resp = answer_fn(case["question"])
        result = CaseResult(case["id"], category, case["question"])
        result.answer = resp.answer
        result.contexts = resp.contexts
        result.flags = resp.flags
        result.latency_ms = resp.timings_ms.get("total")

        if category in ANSWERABLE:
            _score_retrieval(result, resp.sources, resp.contexts, case)

        did_refuse = refused(resp.answer, resp.blocked)
        result.refusal_correct = float(did_refuse == bool(case.get("should_refuse")))

        if not case.get("should_refuse"):
            result.answer_term_match = answer_term_match(
                resp.answer, case.get("expected_answer_terms", []), require_all=category == "comparison"
            )
            if not did_refuse:
                result.citation_count = resp.details.get("citation_count")
                result.numeric_grounding = resp.details.get("numeric_grounding")

        if case.get("expected_flag"):
            result.flag_correct = float(case["expected_flag"] in resp.flags)

        results.append(result)

    answerable = [r for r in results if r.category in ANSWERABLE]
    unanswerable = [r for r, c in zip(results, cases) if c.get("should_refuse")]
    latencies = [r.latency_ms for r in results if r.latency_ms]
    generated = [r for r in answerable if r.citation_count is not None]

    return EvalReport(
        mode="rag",
        num_cases=len(results),
        summary={
            "hit_at_k": _mean([r.hit_at_k for r in answerable]),
            "mrr": _mean([r.mrr for r in answerable]),
            "target_coverage": _mean([r.target_coverage for r in answerable]),
            "keyword_recall_at_k": _mean([r.keyword_recall_at_k for r in answerable]),
            "answer_correctness": _mean([r.answer_term_match for r in answerable]),
            "abstention_accuracy": _mean([r.refusal_correct for r in unanswerable]),
            "over_refusal_rate": _mean([1 - r.refusal_correct for r in answerable]),
            "guardrail_flag_accuracy": _mean([r.flag_correct for r in results]),
            "citation_rate": _mean([float((r.citation_count or 0) > 0) for r in generated]),
            "numeric_grounding": _mean([r.numeric_grounding for r in generated]),
            "latency_p50_ms": _pct(latencies, 0.5),
            "latency_p95_ms": _pct(latencies, 0.95),
        },
        cases=results,
    )


def format_report(report: EvalReport) -> str:
    lines = [f"Finsight evaluation ({report.mode})", "=" * 52, f"Cases scored          : {report.num_cases}"]
    for key, value in report.summary.items():
        if value is None:
            continue
        shown = f"{value:.0f} ms" if key.endswith("_ms") else (f"{value:.3f}" if key == "mrr" else f"{value:.1%}")
        lines.append(f"{key:<22}: {shown}")

    lines += ["", "Per-case", "-" * 52]
    for c in report.cases:
        parts = [f"[{c.id}]"]
        if c.hit_at_k is not None:
            parts.append(f"hit={c.hit_at_k:.0f} cov={c.target_coverage:.0%}")
        if c.keyword_recall_at_k is not None:
            parts.append(f"kw={c.keyword_recall_at_k:.0%}")
        if c.answer_term_match is not None:
            parts.append(f"ans={c.answer_term_match:.0f}")
        if c.refusal_correct is not None:
            parts.append(f"refusal_ok={c.refusal_correct:.0f}")
        if c.flag_correct is not None:
            parts.append(f"flag_ok={c.flag_correct:.0f}")
        if c.numeric_grounding is not None:
            parts.append(f"num_grounded={c.numeric_grounding:.0%}")
        lines.append(" ".join(parts))
    return "\n".join(lines)
