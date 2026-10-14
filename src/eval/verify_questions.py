"""Live, uncached gold-case checks. Requires an explicitly configured provider key.

Records actual answers, citations and wall times. Never writes keys or feedback
tokens. Passing automated checks is not a guarantee of future model output.
"""
import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
import time

from src.config import ROOT_DIR
from src.guardrails import cited_indices, extract_numbers
from src.runtime import generator_identity
from src.verification import configuration_fingerprint


def has_term(answer, term):
    try:
        value = Decimal(term.rstrip("%"))
    except InvalidOperation:
        return re.sub(r"\s+", " ", term.lower()) in re.sub(r"\s+", " ", answer.lower())
    return value in {Decimal(n) for n in extract_numbers(answer)}


def validate(case, answer):
    references = set(cited_indices(answer.answer))
    sources = {s.id: s for s in answer.sources}
    if answer.blocked or answer.flags or not references or not references <= sources.keys():
        return False
    if not all(has_term(answer.answer, term) for term in case["expected_answer_terms"]):
        return False
    for source_id in references:
        source = sources[source_id]
        if (source.company, source.quarter, source.year) != (
            case["expected_company"], case["expected_quarter"], case["expected_year"]):
            return False
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--limit", type=int, default=4)
    parser.add_argument("--output", type=Path, default=ROOT_DIR / ".e2e" / "gemini-verification.json")
    parser.add_argument("--publish", action="store_true", help="Publish passing examples for this exact configuration")
    args = parser.parse_args()
    if not 2 <= args.runs <= 5 or not 1 <= args.limit <= 20:
        parser.error("Use 2–5 runs and 1–20 cases")
    from src.chat import answer_chat, ChatRequest
    from src.retrieval import get_retriever
    from src.llm import get_llm
    started = time.perf_counter()
    get_retriever()
    get_llm()
    startup_ms = (time.perf_counter() - started) * 1000
    cases = json.loads((ROOT_DIR / "src/eval/cases.json").read_text())
    desired = ["msft_revenue_fy25_q1", "msft_eps_fy25_q1", "meta_revenue_q1_2025", "msft_cloud_fy25_q1"]
    selected = [next(c for c in cases if c["id"] == key) for key in desired][:args.limit]
    results, verified = [], []
    for case in selected:
        runs = []
        for index in range(args.runs):
            t = time.perf_counter()
            try:
                answer = answer_chat(ChatRequest(question=case["question"]), use_cache=False)
                elapsed = (time.perf_counter() - t) * 1000
                runs.append({"valid": validate(case, answer), "wall_ms": round(elapsed, 2),
                    "answer": answer.answer, "blocked": answer.blocked, "flags": answer.flags,
                    "timings_ms": answer.timings_ms,
                    "sources": [s.model_dump(mode="json") for s in answer.sources]})
                print(f"{case['id']} run {index + 1}: valid={runs[-1]['valid']}, {elapsed:.0f}ms", flush=True)
            except Exception:
                runs.append({"valid": False, "wall_ms": round((time.perf_counter() - t) * 1000, 2),
                             "error": "Provider or pipeline failed; inspect sanitized backend logs."})
                print(f"{case['id']} run {index + 1}: failed", flush=True)
            # Avoid bursting free-tier request limits; wait is outside measured request time.
            if index + 1 < args.runs:
                time.sleep(2)
        passed = all(r["valid"] and r["wall_ms"] < 5000 for r in runs)
        results.append({"id": case["id"], "question": case["question"], "reference": case["reference"],
                        "passed": passed, "runs": runs})
        if passed:
            verified.append({"id": case["id"], "question": case["question"],
                             "max_ms": max(r["wall_ms"] for r in runs), "runs": len(runs)})
    report = {"model": generator_identity(), "configuration": configuration_fingerprint(),
              "checked_at": datetime.now(timezone.utc).isoformat(), "startup_ms": round(startup_ms, 2),
              "notice": "Automated repeated checks against gold references and citations; not a promise of perfect output.",
              "results": results, "questions": verified}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.publish:
        public = {key: report[key] for key in ("model", "configuration", "checked_at", "notice", "questions")}
        (ROOT_DIR / "verified_questions.json").write_text(json.dumps(public, indent=2), encoding="utf-8")
    print(f"Passed {len(verified)}/{len(selected)}; report: {args.output}")


if __name__ == "__main__":
    main()
