"""Export local review aggregates without invoking any model or exposing answer tokens."""
import argparse
import json
import os
from pathlib import Path

from src.config import ROOT_DIR
from src.feedback import FeedbackStore


def main():
    parser = argparse.ArgumentParser(description="Export Finsight answer feedback aggregates")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    store = FeedbackStore(Path(os.getenv("FINSIGHT_FEEDBACK_DB", str(ROOT_DIR / "feedback.sqlite3"))))
    report = store.summary()
    report["notice"] = "Counts describe submitted user reviews, not objective financial accuracy. Categories can overlap."
    payload = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)


if __name__ == "__main__":
    main()
