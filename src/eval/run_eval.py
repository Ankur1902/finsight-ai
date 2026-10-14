"""Run Finsight evaluation.

Examples:
    python -m src.eval.run_eval --retrieval-only          # fast, no LLM
    python -m src.eval.run_eval --full                    # retrieval + generation + guardrails
    python -m src.eval.run_eval --full --ragas            # + RAGAS (needs ANTHROPIC_API_KEY for the judge)
    python -m src.eval.run_eval --full --category factoid --output eval_results.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.eval.dataset import EVAL_CASES
from src.eval.metrics import evaluate_rag, evaluate_retrieval, format_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Finsight RAG pipeline")
    parser.add_argument("--retrieval-only", action="store_true", help="Score retriever only (no LLM)")
    parser.add_argument("--full", action="store_true", help="Score retrieval + generation + guardrails")
    parser.add_argument("--ragas", action="store_true", help="Also run RAGAS LLM-judged metrics (implies --full)")
    parser.add_argument("--category", help="Only run cases of this category (factoid, comparison, refusal, guardrail)")
    parser.add_argument("--output", type=Path, default=None, help="Write JSON report here")
    args = parser.parse_args()

    cases = [c for c in EVAL_CASES if not args.category or c.get("category") == args.category]
    from src.retrieval import get_retriever

    if args.full or args.ragas:
        from src.rag import answer_question

        report = evaluate_rag(answer_question, cases)
    else:
        report = evaluate_retrieval(get_retriever(), cases)

    print(format_report(report))
    payload = report.to_dict()

    if args.ragas:
        from src.eval.ragas_eval import run_ragas

        ragas_scores = run_ragas(report, cases)
        payload["ragas"] = ragas_scores
        print("\nRAGAS (LLM-judged)")
        print("-" * 52)
        for key, value in ragas_scores["summary"].items():
            print(f"{key:<22}: {value:.3f}" if value is not None else f"{key:<22}: n/a")

    if args.output:
        args.output.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        print(f"\nSaved report to {args.output}")


if __name__ == "__main__":
    main()
