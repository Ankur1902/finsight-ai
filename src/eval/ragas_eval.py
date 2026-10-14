"""RAGAS (LLM-as-judge) metrics on top of a `evaluate_rag` report.

Metrics (ragas>=0.4 collections API):
  faithfulness       - are the answer's claims supported by the retrieved contexts?
  answer_relevancy   - does the answer address the question (penalises evasive answers)?
  context_precision  - are the relevant chunks ranked high (uses the reference answer)?
  context_recall     - do the contexts contain everything the reference answer needs?
  factual_correctness- claim-level F1 of the answer against the reference answer

The judge is Claude (FINSIGHT_JUDGE_MODEL, default claude-sonnet-5) and needs
ANTHROPIC_API_KEY. A 0.5B local model cannot follow RAGAS's structured-output
prompts reliably, so there is deliberately no local-judge fallback: a noisy judge
is worse than none. Embeddings for answer_relevancy stay local (bge-m3).
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from src.config import EMBEDDING_MODEL, JUDGE_MODEL
from src.eval.metrics import EvalReport

JUDGED_CATEGORIES = {"factoid", "comparison"}


def _judge_llm():
    import anthropic
    from ragas.llms import llm_factory

    llm = llm_factory(JUDGE_MODEL, provider="anthropic", client=anthropic.AsyncAnthropic(), max_tokens=4096)
    # ragas defaults to temperature/top_p, which current Claude models reject, and
    # Instructor forces a tool call, which must not be combined with thinking.
    llm.model_args.pop("temperature", None)
    llm.model_args.pop("top_p", None)
    llm.model_args["thinking"] = {"type": "disabled"}
    return llm


def _embeddings():
    from ragas.embeddings.huggingface_provider import HuggingFaceEmbeddings

    return HuggingFaceEmbeddings(model=EMBEDDING_MODEL, normalize_embeddings=True)


async def _score_case(metrics: dict, sem: asyncio.Semaphore, q: str, a: str, ctx: list[str], ref: str) -> dict:
    async def run(name, coro):
        async with sem:
            try:
                return name, float((await coro).value)
            except Exception as exc:  # one flaky judgement shouldn't sink the run
                # SDK exceptions may contain request bodies or credentials.
                return name, f"error: {type(exc).__name__}"

    jobs = [
        run("faithfulness", metrics["faithfulness"].ascore(user_input=q, response=a, retrieved_contexts=ctx)),
        run("answer_relevancy", metrics["answer_relevancy"].ascore(user_input=q, response=a)),
        run("context_precision", metrics["context_precision"].ascore(user_input=q, reference=ref, retrieved_contexts=ctx)),
        run("context_recall", metrics["context_recall"].ascore(user_input=q, retrieved_contexts=ctx, reference=ref)),
        run("factual_correctness", metrics["factual_correctness"].ascore(response=a, reference=ref)),
    ]
    return dict(await asyncio.gather(*jobs))


async def _run(report: EvalReport, cases: list[dict[str, Any]], concurrency: int) -> dict[str, Any]:
    from ragas.metrics.collections import (
        AnswerRelevancy,
        ContextPrecisionWithReference,
        ContextRecall,
        FactualCorrectness,
        Faithfulness,
    )

    llm = _judge_llm()
    metrics = {
        "faithfulness": Faithfulness(llm=llm),
        "answer_relevancy": AnswerRelevancy(llm=llm, embeddings=_embeddings()),
        "context_precision": ContextPrecisionWithReference(llm=llm),
        "context_recall": ContextRecall(llm=llm),
        "factual_correctness": FactualCorrectness(llm=llm, mode="f1"),
    }
    sem = asyncio.Semaphore(concurrency)
    by_id = {c["id"]: c for c in cases}

    judged = [
        r for r in report.cases
        if r.category in JUDGED_CATEGORIES and r.answer and r.contexts and by_id[r.id].get("reference")
    ]
    scores = await asyncio.gather(
        *(_score_case(metrics, sem, r.question, r.answer, r.contexts, by_id[r.id]["reference"]) for r in judged)
    )

    per_case = {r.id: s for r, s in zip(judged, scores)}
    summary = {}
    for name in metrics:
        values = [s[name] for s in scores if isinstance(s.get(name), float)]
        summary[name] = sum(values) / len(values) if values else None
    return {"judge": JUDGE_MODEL, "num_cases": len(judged), "summary": summary, "cases": per_case}


def run_ragas(report: EvalReport, cases: list[dict[str, Any]], concurrency: int = 4) -> dict[str, Any]:
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit(
            "RAGAS needs a capable judge LLM. Set ANTHROPIC_API_KEY (judge model: "
            f"{JUDGE_MODEL}, override with FINSIGHT_JUDGE_MODEL)."
        )
    return asyncio.run(_run(report, cases, concurrency))
