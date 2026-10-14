"""Only serve benchmark-passing questions for the active corpus/configuration."""
import json
import math
from datetime import datetime, timedelta, timezone
from .config import ROOT_DIR
from .verification import configuration_fingerprint


def verified_questions():
    try:
        report = json.loads((ROOT_DIR / "verified_questions.json").read_text(encoding="utf-8"))
        if not isinstance(report, dict):
            return {"questions": []}
        if report.get("configuration") != configuration_fingerprint():
            return {"questions": []}
        checked = datetime.fromisoformat(report.get("checked_at", ""))
        now = datetime.now(timezone.utc)
        if checked.tzinfo is None or checked > now or now - checked > timedelta(days=7):
            return {"questions": []}
        rows = report.get("questions", [])
        if not isinstance(rows, list) or len(rows) > 20 or not all(
            isinstance(r, dict) and isinstance(r.get("id"), str) and 0 < len(r["id"]) <= 100
            and isinstance(r.get("question"), str) and 0 < len(r["question"].strip()) <= 1000
            and type(r.get("max_ms")) in (int, float) and math.isfinite(r["max_ms"])
            and 0 <= r["max_ms"] < 5000 and type(r.get("runs")) is int and 2 <= r["runs"] <= 5
            for r in rows
        ) or len({r["id"] for r in rows}) != len(rows):
            return {"questions": []}
        # Publish only public fields, never arbitrary additions in the local file.
        public = [{key: row[key] for key in ("id", "question", "max_ms", "runs")} for row in rows]
        return {"questions": public, "checked_at": report["checked_at"], "model": report.get("model")}
    except (OSError, ValueError, TypeError):
        return {"questions": []}
