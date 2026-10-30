"""Stateless HTTP adapter for the existing grounded RAG pipeline."""
from __future__ import annotations

from collections.abc import Callable
from math import isfinite
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .config import MAX_QUESTION_CHARS
from .guardrails import check_input, is_injection, redact_pii
from .query_planner import plan_query
from .runtime import inference_context


class HistoryMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=12)
    agentic: bool = False  # let a calculator tool compute derived figures


class ChatSource(BaseModel):
    id: int = Field(ge=1)
    source: str
    company: str | None = None
    company_name: str | None = None
    quarter: str | None = None
    year: str | None = None
    period: str | None = None
    call_date: str | None = None
    page: int | None = Field(default=None, ge=1)
    score: float | None = None
    snippet: str
    excerpt: str


class ChatTarget(BaseModel):
    company: str | None = None
    quarter: str | None = None
    year: str | None = None
    label: str


class ChatPlan(BaseModel):
    targets: list[ChatTarget]
    inherited: bool


class ChatAnswer(BaseModel):
    cached: bool = False
    model: str | None = None
    response_id: str | None = None
    feedback_token: str | None = Field(default=None, repr=False)
    question: str
    answer: str
    sources: list[ChatSource] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    blocked: bool = False
    plan: ChatPlan | None = None
    timings_ms: dict[str, float] = Field(default_factory=dict)
    claims: list[dict] = Field(default_factory=list)
    claim_summary: dict | None = None
    calculations: list[dict] = Field(default_factory=list)
    route: str | None = None


def answer_chat(request: ChatRequest, *, retriever_factory: Callable | None = None, rag_function: Callable | None = None, use_cache=True) -> ChatAnswer:
    guard = check_input(request.question)
    if not guard.allowed:
        safe_question, pii = redact_pii(guard.text)
        flags = list(dict.fromkeys([*guard.flags, *(f"pii_redacted:{kind}" for kind in pii)]))
        return ChatAnswer(question=safe_question, answer=guard.message or "Please enter an earnings-call question.", flags=flags, blocked=True)

    # Conversation context is untrusted and bounded. No conversation is shared
    # between users, and caller-provided retrieval plans are never accepted.
    history = []
    for message in request.history:
        text, _ = redact_pii(message.content)
        if not is_injection(text):
            history.append({"role": message.role, "content": text})

    with inference_context():
        if retriever_factory is None:
            from .retrieval import get_retriever
            retriever_factory = get_retriever
        if rag_function is None:
            from .rag import answer_question
            rag_function = answer_question
        retriever = retriever_factory()
        previous = None
        for message in history:
            if message["role"] == "user":
                previous_input = check_input(message["content"])
                if previous_input.allowed:
                    previous = plan_query(previous_input.text, retriever.catalog, previous)
        arguments = dict(history=history, previous_plan=previous, retriever=retriever)
        if request.agentic:
            arguments["tools"] = True
        if not use_cache:
            arguments["use_cache"] = False
        response = rag_function(request.question, **arguments)

    if not response.answer.strip():
        raise RuntimeError("The generator returned an empty answer")

    sources = []
    for index, record in enumerate(response.sources):
        context = response.contexts[index] if index < len(response.contexts) else record.get("snippet", "")
        excerpt = record.get("excerpt") or context
        if not record.get("excerpt") and excerpt.startswith("[") and "earnings call" in excerpt.split("\n", 1)[0]:
            excerpt = excerpt.split("\n", 1)[1]
        page = record.get("page")
        score = record.get("score")
        sources.append(ChatSource(
            id=record.get("id", index + 1), source=record.get("source", "unknown"),
            company=record.get("company"), company_name=record.get("company_name"),
            quarter=record.get("quarter"), year=str(record["year"]) if record.get("year") else None,
            period=record.get("period"), call_date=record.get("call_date"),
            page=page if isinstance(page, int) and page > 0 else None,
            score=float(score) if isinstance(score, (float, int)) and isfinite(score) else None,
            snippet=record.get("snippet", excerpt[:400]), excerpt=excerpt,
        ))
    plan = None
    if response.plan:
        labels = {"meta": "Meta", "microsoft": "Microsoft", "nvda": "NVIDIA"}
        plan = ChatPlan(inherited=response.plan.inherited, targets=[
            ChatTarget(company=t.company, quarter=t.quarter, year=t.year,
                       label=" ".join(filter(None, [labels.get(t.company, t.company or "All companies"), t.quarter, f"FY{t.year}" if t.year else None])))
            for t in response.plan.targets
        ])
    return ChatAnswer(cached=bool(getattr(response, "details", {}).get("cached")), model=getattr(response, "details", {}).get("model"), question=response.question, answer=response.answer, sources=sources,
                      flags=response.flags, blocked=response.blocked, plan=plan, timings_ms=response.timings_ms,
                      claims=getattr(response, "details", {}).get("claims", []),
                      claim_summary=getattr(response, "details", {}).get("claim_summary"),
                      calculations=getattr(response, "details", {}).get("calculations", []),
                      route=getattr(response, "details", {}).get("route"))
