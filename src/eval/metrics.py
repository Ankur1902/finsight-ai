from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any


REFUSAL_PHRASE = "couldn't find that information in the provided documents"


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


COMPANY_ALIASES = {
    "nvidia": "nvda",
    "nvda": "nvda",
    "meta": "meta",
    "microsoft": "microsoft",
}


def _normalize_company(name: str) -> str:
    key = name.lower()
    return COMPANY_ALIASES.get(key, key)


def _chunk_matches_company(chunk_meta: dict[str, Any], company: str | None) -> bool:
    if not company:
        return False
    return _normalize_company(chunk_meta.get("company", "")) == _normalize_company(
        company
    )


def _chunk_matches_period(
    chunk_meta: dict[str, Any],
    quarter: str | None,
    year: str | None,
) -> bool:
    if quarter and chunk_meta.get("quarter", "").upper() != quarter.upper():
        return False
    if year and str(chunk_meta.get("year", "")) != str(year):
        return False
    return True


def _is_relevant_chunk(
    chunk_meta: dict[str, Any],
    case: dict[str, Any],
) -> bool:
    company = case.get("expected_company")
    if company and not _chunk_matches_company(chunk_meta, company):
        return False

    quarter = case.get("expected_quarter")
    year = case.get("expected_year")
    if (quarter or year) and not _chunk_matches_period(chunk_meta, quarter, year):
        return False

    return bool(company or quarter or year)


def keyword_recall(text: str, keywords: list[str]) -> float | None:
    if not keywords:
        return None
    normalized = _normalize(text)
    hits = sum(1 for kw in keywords if kw.lower() in normalized)
    return hits / len(keywords)


def hit_at_k(relevant_flags: list[bool]) -> float:
    return 1.0 if any(relevant_flags) else 0.0


def mrr(relevant_flags: list[bool]) -> float:
    for idx, is_relevant in enumerate(relevant_flags, start=1):
        if is_relevant:
            return 1.0 / idx
    return 0.0


def precision_at_k(relevant_flags: list[bool]) -> float:
    if not relevant_flags:
        return 0.0
    return sum(relevant_flags) / len(relevant_flags)


def answer_term_match(answer: str, terms: list[str]) -> float:
    if not terms:
        return 1.0
    normalized = _normalize(answer)
    return 1.0 if any(_normalize(term) in normalized for term in terms) else 0.0


def refused_to_answer(answer: str) -> bool:
    return REFUSAL_PHRASE in _normalize(answer)


@dataclass
class CaseResult:
    id: str
    question: str
    hit_at_k: float
    mrr: float
    precision_at_k: float
    keyword_recall_at_k: float | None
    retrieved_sources: list[str] = field(default_factory=list)
    answer_term_match: float | None = None
    refused: bool | None = None
    latency_ms: float | None = None
    answer_preview: str | None = None


@dataclass
class EvalReport:
    mode: str
    num_cases: int
    hit_rate_at_k: float
    mean_reciprocal_rank: float
    mean_precision_at_k: float
    mean_keyword_recall_at_k: float | None = None
    mean_answer_term_match: float | None = None
    refusal_accuracy: float | None = None
    mean_latency_ms: float | None = None
    cases: list[CaseResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["cases"] = [asdict(case) for case in self.cases]
        return payload


def evaluate_retrieval(retriever, cases: list[dict[str, Any]]) -> EvalReport:
    case_results: list[CaseResult] = []

    for case in cases:
        docs = retriever.invoke(case["question"])
        relevant_flags = [
            _is_relevant_chunk(doc.metadata, case) for doc in docs
        ]

        context = "\n\n".join(doc.page_content for doc in docs)
        keywords = case.get("expected_keywords", [])

        case_results.append(
            CaseResult(
                id=case["id"],
                question=case["question"],
                hit_at_k=hit_at_k(relevant_flags),
                mrr=mrr(relevant_flags),
                precision_at_k=precision_at_k(relevant_flags),
                keyword_recall_at_k=keyword_recall(context, keywords),
                retrieved_sources=[
                    doc.metadata.get("source", "unknown") for doc in docs
                ],
            )
        )

    n = len(case_results)
    return EvalReport(
        mode="retrieval",
        num_cases=n,
        hit_rate_at_k=sum(c.hit_at_k for c in case_results) / n,
        mean_reciprocal_rank=sum(c.mrr for c in case_results) / n,
        mean_precision_at_k=sum(c.precision_at_k for c in case_results) / n,
        mean_keyword_recall_at_k=(
            sum(c.keyword_recall_at_k for c in case_results if c.keyword_recall_at_k is not None)
            / max(1, sum(1 for c in case_results if c.keyword_recall_at_k is not None))
        ),
        cases=case_results,
    )


def evaluate_rag(ask_fn, cases: list[dict[str, Any]]) -> EvalReport:
    case_results: list[CaseResult] = []
    refusal_cases = [c for c in cases if c.get("should_refuse")]

    for case in cases:
        start = time.perf_counter()
        answer, sources = ask_fn(case["question"])
        latency_ms = (time.perf_counter() - start) * 1000

        answer_str = answer if isinstance(answer, str) else str(answer)
        docs_meta = [{"source": s.get("source", "")} for s in sources]
        relevant_flags = [
            _is_relevant_chunk(meta, case) for meta in docs_meta
        ]

        refused = refused_to_answer(answer_str)
        should_refuse = case.get("should_refuse", False)

        case_results.append(
            CaseResult(
                id=case["id"],
                question=case["question"],
                hit_at_k=hit_at_k(relevant_flags),
                mrr=mrr(relevant_flags),
                precision_at_k=precision_at_k(relevant_flags),
                keyword_recall_at_k=keyword_recall(
                    answer_str,
                    case.get("expected_answer_terms", []),
                )
                if not should_refuse
                else (1.0 if refused else 0.0),
                retrieved_sources=[s.get("source", "unknown") for s in sources],
                answer_term_match=answer_term_match(
                    answer_str,
                    case.get("expected_answer_terms", []),
                ),
                refused=refused,
                latency_ms=latency_ms,
                answer_preview=answer_str[:160],
            )
        )

    n = len(case_results)
    refusal_accuracy = None
    if refusal_cases:
        refused_scores = [
            c.keyword_recall_at_k
            for c in case_results
            if any(rc["id"] == c.id for rc in refusal_cases)
        ]
        refusal_accuracy = sum(refused_scores) / len(refused_scores)

    answer_term_scores = [
        c.answer_term_match
        for c in case_results
        if c.answer_term_match is not None
        and not any(ac["id"] == c.id for ac in refusal_cases)
    ]

    return EvalReport(
        mode="rag",
        num_cases=n,
        hit_rate_at_k=sum(c.hit_at_k for c in case_results) / n,
        mean_reciprocal_rank=sum(c.mrr for c in case_results) / n,
        mean_precision_at_k=sum(c.precision_at_k for c in case_results) / n,
        mean_keyword_recall_at_k=(
            sum(c.keyword_recall_at_k for c in case_results if c.keyword_recall_at_k is not None)
            / max(1, sum(1 for c in case_results if c.keyword_recall_at_k is not None))
        ),
        mean_answer_term_match=(
            sum(answer_term_scores) / len(answer_term_scores)
            if answer_term_scores
            else None
        ),
        refusal_accuracy=refusal_accuracy,
        mean_latency_ms=sum(c.latency_ms or 0 for c in case_results) / n,
        cases=case_results,
    )


def format_report(report: EvalReport) -> str:
    lines = [
        f"Finsight RAG Evaluation ({report.mode})",
        "=" * 44,
        f"Cases evaluated : {report.num_cases}",
        f"Hit@k           : {report.hit_rate_at_k:.2%}",
        f"MRR             : {report.mean_reciprocal_rank:.3f}",
        f"Precision@k     : {report.mean_precision_at_k:.2%}",
    ]

    if report.mean_keyword_recall_at_k is not None:
        lines.append(
            f"Keyword recall@k: {report.mean_keyword_recall_at_k:.2%}"
        )

    if report.mean_answer_term_match is not None:
        lines.append(
            f"Answer term match: {report.mean_answer_term_match:.2%}"
        )
    if report.refusal_accuracy is not None:
        lines.append(f"Refusal accuracy : {report.refusal_accuracy:.2%}")
    if report.mean_latency_ms is not None:
        lines.append(f"Mean latency     : {report.mean_latency_ms:.0f} ms")

    lines.append("")
    lines.append("Per-case summary")
    lines.append("-" * 44)
    for case in report.cases:
        kw = "n/a" if case.keyword_recall_at_k is None else f"{case.keyword_recall_at_k:.0%}"
        lines.append(
            f"[{case.id}] hit={case.hit_at_k:.0f} "
            f"kw={kw} "
            f"sources={', '.join(case.retrieved_sources[:2])}"
        )

    return "\n".join(lines)
