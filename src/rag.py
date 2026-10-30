"""RAG pipeline: guard input -> plan -> retrieve -> guard retrieval -> generate -> guard output."""

from __future__ import annotations

import json
import hashlib
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from langchain_core.documents import Document

from . import guardrails
from .config import ROOT_DIR
from typing import TYPE_CHECKING
from .retrieval import get_retriever as get_hybrid_retriever
if TYPE_CHECKING:
    from .hybrid_retriever import HybridRetriever
from .llm import get_llm
from .answer_cache import ANSWERS
from .config import MAX_NEW_TOKENS, GEMINI_THINKING_LEVEL
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .query_planner import QueryPlan, plan_query
from .observability import METRICS, estimate_tokens, span
from .semantic_cache import SEMANTIC
from . import agent, claims as claim_checks

TRACE_FILE = Path(os.getenv("FINSIGHT_TRACE_FILE", str(ROOT_DIR / "logs" / "traces.jsonl")))
COMPANY_LABELS = {"meta": "Meta", "microsoft": "Microsoft", "nvda": "NVIDIA"}


@dataclass
class RAGResponse:
    question: str
    answer: str
    sources: list[dict] = field(default_factory=list)
    contexts: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    blocked: bool = False
    plan: QueryPlan | None = None
    timings_ms: dict[str, float] = field(default_factory=dict)
    details: dict = field(default_factory=dict)


def _source_record(i: int, doc: Document) -> dict:
    m = doc.metadata
    body = doc.page_content.split("\n", 1)[-1]
    return {
        "id": i,
        "source": m.get("source", "unknown"),
        "company": m.get("company", "unknown"),
        "company_name": m.get("company_name", m.get("company")),
        "quarter": m.get("quarter"),
        "year": m.get("year"),
        "period": m.get("period", "unknown"),
        "call_date": m.get("call_date"),
        "page": m.get("page"),
        "score": round(m.get("rerank_score", m.get("lexical_score", 0.0)), 3),
        "snippet": body[:400],
        "excerpt": body,
    }


def _uncovered_targets(plan: QueryPlan, catalog: dict[str, list[tuple[str, str]]]) -> list[str]:
    missing = []
    for t in plan.targets:
        if not t.company or not (t.quarter or t.year):
            continue
        available = catalog.get(t.company, [])
        hit = any((not t.quarter or q == t.quarter) and (not t.year or y == t.year) for q, y in available)
        if not hit:
            missing.append(t)
    if not missing:
        return []
    lines = []
    for t in missing:
        periods = ", ".join(f"{q} FY{y}" for q, y in catalog.get(t.company, []))
        lines.append(
            f"- {COMPANY_LABELS.get(t.company, t.company)} {t.quarter or ''} FY{t.year} is not in the "
            f"document set. Available: {periods or 'none'}."
        )
    return lines


def _history_text(history: list[dict] | None, turns: int = 2) -> str:
    if not history:
        return ""
    recent = history[-2 * turns :]
    return "\n".join(f"{m['role']}: {m['content'][:500]}" for m in recent)


def _retrieval_query(question: str, plan: QueryPlan) -> str:
    if not plan.inherited:
        return question
    labels = "; ".join(t.label() for t in plan.targets)
    return f"{question} ({labels})"


def _trace(resp: RAGResponse, llm_name: str | None) -> None:
    try:
        TRACE_FILE.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "question": resp.question,  # already PII-redacted
            "llm": llm_name,
            "blocked": resp.blocked,
            "flags": resp.flags,
            "targets": [t.label() for t in resp.plan.targets] if resp.plan else [],
            "sources": [f"{s['source']}#p{s['page']}" for s in resp.sources],
            "timings_ms": resp.timings_ms,
            "details": resp.details,
        }
        with TRACE_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except OSError:
        pass  # tracing must never break answering


def answer_question(
    question: str,
    history: list[dict] | None = None,
    previous_plan: QueryPlan | None = None,
    retriever: HybridRetriever | None = None,
    generate: bool = True,
    use_cache: bool = True,
    tools: bool = False,
) -> RAGResponse:
    t0 = time.perf_counter()
    timings: dict[str, float] = {}

    # 1. Input guardrails ------------------------------------------------
    gin = guardrails.check_input(question)
    resp = RAGResponse(question=gin.text, answer="", flags=list(gin.flags))
    if not gin.allowed:
        resp.answer, resp.blocked = gin.message, True
        _trace(resp, None)
        return resp
    question = gin.text

    # 2. Plan + retrieve --------------------------------------------------
    retriever = retriever or get_hybrid_retriever()
    plan = plan_query(question, retriever.catalog, previous_plan)
    resp.plan = plan

    missing = _uncovered_targets(plan, retriever.catalog)
    if missing and len(missing) == len(plan.targets):
        resp.answer = "That period isn't covered by the transcripts I have:\n" + "\n".join(missing)
        resp.blocked = True
        resp.flags.append("period_not_covered")
        _trace(resp, None)
        return resp
    if missing:
        resp.flags.append("period_partially_covered")

    t = time.perf_counter()
    with span("retrieve"):
        docs = retriever.retrieve(_retrieval_query(question, plan), plan)
    docs, poisoned = guardrails.filter_poisoned_chunks(docs)
    timings["retrieve"] = (time.perf_counter() - t) * 1000
    if poisoned:
        resp.flags.append(f"poisoned_chunks_removed:{poisoned}")

    resp.sources = [_source_record(i, d) for i, d in enumerate(docs, start=1)]
    resp.contexts = [d.page_content for d in docs]

    # 3. Retrieval guardrail (abstain on weak evidence) --------------------
    gret = guardrails.check_retrieval(docs)
    resp.details.update(gret.details)
    if not gret.allowed:
        resp.answer, resp.blocked = gret.message, True
        resp.flags += gret.flags
        timings["total"] = (time.perf_counter() - t0) * 1000
        resp.timings_ms = timings
        _trace(resp, None)
        return resp

    if not generate:
        timings["total"] = (time.perf_counter() - t0) * 1000
        resp.timings_ms = timings
        return resp

    # 4. Generate -----------------------------------------------------------
    llm = get_llm()
    resp.details["model"] = llm.name
    semantic_scope = None
    if use_cache and os.getenv("FINSIGHT_SEMANTIC_CACHE") == "1" and not history:
        semantic_scope = json.dumps([llm.name, tools, hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
                                     [t.label() for t in plan.targets]])
        sem_hit = SEMANTIC.get(semantic_scope, question)
        if sem_hit is not None:
            METRICS.inc("semantic_cache_hit")
            sem_hit.details["cached"] = True
            sem_hit.timings_ms = {**timings, "total": (time.perf_counter() - t0) * 1000}
            _trace(sem_hit, llm.name)
            return sem_hit
    calcs, calc_rejected = [], []
    if tools:
        with span("calculate"):
            calcs, calc_rejected = agent.plan_and_compute(llm, question, docs)
        resp.details["calculations"] = calcs
        if calc_rejected:
            resp.details["calculations_rejected"] = len(calc_rejected)
    prompt = build_user_prompt(question, docs, _history_text(history))
    if calcs:
        prompt = agent.calculation_block(calcs) + "\n\n" + prompt
    cache_key = hashlib.sha256(json.dumps([llm.name, MAX_NEW_TOKENS,
        GEMINI_THINKING_LEVEL, SYSTEM_PROMPT, prompt], sort_keys=True).encode()).hexdigest()
    hit = ANSWERS.get(cache_key) if use_cache else None
    if hit is not None:
        hit.timings_ms = {**timings, "total": (time.perf_counter() - t0) * 1000}
        hit.details["cached"] = True
        _trace(hit, llm.name)
        return hit
    t = time.perf_counter()
    with span("generate"):
        raw = llm.generate(SYSTEM_PROMPT, prompt)
    timings["generate"] = (time.perf_counter() - t) * 1000
    route = getattr(llm, "last_route", None) or "single"
    used_model = getattr(llm, "last_model", None) or llm.name
    resp.details["model"], resp.details["route"] = used_model, route
    METRICS.record_request(route=route, model=used_model, tokens_in=estimate_tokens(SYSTEM_PROMPT + prompt),
                           tokens_out=estimate_tokens(raw))

    # 5. Output guardrails ---------------------------------------------------
    advice = "investment_advice_request" in resp.flags
    with span("guard_output"):
        gout = guardrails.check_output(raw, docs, advice_requested=advice,
                                       extra_numbers=agent.calculation_numbers(calcs) if calcs else None)
    resp.answer = gout.text
    resp.blocked = not gout.allowed
    resp.flags += gout.flags
    resp.details.update(gout.details)
    if missing:
        resp.answer += "\n\n_Note:_\n" + "\n".join(missing)
    if not resp.blocked:
        with span("verify_claims"):
            verified = claim_checks.verify_claims(
                resp.answer, docs, extra_numbers=agent.calculation_numbers(calcs) if calcs else None)
        resp.details["claims"] = claim_checks.claims_as_dicts(verified)
        resp.details["claim_summary"] = claim_checks.summarize(verified)
        if resp.details["claim_summary"]["unsupported"]:
            resp.flags.append("unsupported_claims")
            METRICS.inc("unsupported_claims")

    timings["total"] = (time.perf_counter() - t0) * 1000
    resp.timings_ms = timings
    if use_cache:
        ANSWERS.put(cache_key, resp)
        if semantic_scope:
            SEMANTIC.put(semantic_scope, question, resp)
    _trace(resp, llm.name)
    return resp


# Backwards-compatible helpers ------------------------------------------------


def retrieve(question: str) -> list[Document]:
    return get_hybrid_retriever().retrieve(question)


def ask(question: str):
    resp = answer_question(question)
    return resp.answer, resp.sources


def response_to_dict(resp: RAGResponse) -> dict:
    data = asdict(resp)
    data["plan"] = [t.label() for t in resp.plan.targets] if resp.plan else []
    return data
