"""Run Finsight RAG evaluation.

Examples:
    python -m src.eval.run_eval --retrieval-only
    python -m src.eval.run_eval --full
    python -m src.eval.run_eval --retrieval-only --output eval_results.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.eval.dataset import EVAL_CASES
from src.eval.metrics import evaluate_rag, evaluate_retrieval, format_report
from src.rag import ask
from src.vectorstore import get_retriever


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Finsight RAG pipeline")
    parser.add_argument(
        "--retrieval-only",
        action="store_true",
        help="Score retriever only (fast; no LLM load)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Score retrieval + generation (loads local LLM)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write JSON report",
    )
    args = parser.parse_args()

    if not args.retrieval_only and not args.full:
        args.retrieval_only = True

    if args.retrieval_only:
        report = evaluate_retrieval(get_retriever(), EVAL_CASES)
    else:
        report = evaluate_rag(ask, EVAL_CASES)

    print(format_report(report))

    if args.output:
        args.output.write_text(
            json.dumps(report.to_dict(), indent=2),
            encoding="utf-8",
        )
        print(f"\nSaved report to {args.output}")


if __name__ == "__main__":
    main()
