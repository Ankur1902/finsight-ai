"""Local answer review storage. Feedback is untrusted review data, never model instructions."""
from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .guardrails import redact_pii

Rating = Literal["helpful", "needs_improvement"]
Category = Literal["accuracy", "relevance", "clarity", "citations", "missing_context", "fiscal_period", "units"]


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    response_id: str = Field(pattern=r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$")
    feedback_token: str = Field(min_length=32, max_length=128, repr=False)
    submission_id: str = Field(pattern=r"^[A-Za-z0-9_-]{12,96}$")
    rating: Rating
    categories: list[Category] = Field(default_factory=list, max_length=7)
    note: str = Field(default="", max_length=1600)
    source_ids: list[int] = Field(default_factory=list, max_length=48)

    @model_validator(mode="after")
    def validate_details(self):
        if len(set(self.categories)) != len(self.categories):
            raise ValueError("Choose each feedback category once.")
        if len(set(self.source_ids)) != len(self.source_ids) or any(i < 1 for i in self.source_ids):
            raise ValueError("Source references must be unique positive numbers.")
        if self.rating == "needs_improvement" and not self.categories:
            raise ValueError("Choose at least one area that needs improvement.")
        self.note = self.note.strip()
        return self


class FeedbackReceipt(BaseModel):
    status: Literal["saved"] = "saved"
    response_id: str
    submission_id: str
    rating: Rating
    note_redacted: bool


class FeedbackError(ValueError):
    def __init__(self, detail: str, status_code: int = 422):
        super().__init__(detail)
        self.status_code = status_code


class FeedbackStore:
    def __init__(self, path: Path, retention_days: int = 30):
        if not 1 <= retention_days <= 365:
            raise ValueError("Feedback retention must be between 1 and 365 days.")
        self.path = Path(path)
        self.retention_seconds = retention_days * 86400

    @contextmanager
    def _connection(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys = ON")
            db.execute("PRAGMA journal_mode = WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS answers (
                    response_id TEXT PRIMARY KEY, token_hash TEXT NOT NULL,
                    snapshot TEXT NOT NULL, model TEXT NOT NULL,
                    created_at TEXT NOT NULL, expires_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS answers_expiry ON answers(expires_at);
                CREATE TABLE IF NOT EXISTS feedback (
                    response_id TEXT PRIMARY KEY REFERENCES answers(response_id) ON DELETE CASCADE,
                    rating TEXT NOT NULL CHECK(rating IN ('helpful', 'needs_improvement')),
                    categories TEXT NOT NULL, note TEXT NOT NULL, source_ids TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS feedback_receipts (
                    submission_id TEXT PRIMARY KEY,
                    response_id TEXT NOT NULL REFERENCES answers(response_id) ON DELETE CASCADE,
                    payload_hash TEXT NOT NULL, receipt TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS receipt_answers ON feedback_receipts(response_id);
            """)
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def register(self, snapshot: dict, model: str) -> tuple[str, str]:
        response_id, token = str(uuid4()), secrets.token_urlsafe(32)
        safe_snapshot = {k: v for k, v in snapshot.items() if k not in {"feedback_token", "response_id"}}
        if "question" in safe_snapshot:
            safe_snapshot["question"] = redact_pii(str(safe_snapshot["question"]))[0]
        now = int(time.time())
        with self._connection() as db:
            db.execute("DELETE FROM answers WHERE expires_at <= ?", (now,))
            db.execute("INSERT INTO answers VALUES (?, ?, ?, ?, ?, ?)", (
                response_id, hashlib.sha256(token.encode()).hexdigest(),
                json.dumps(safe_snapshot, allow_nan=False), model,
                datetime.now(timezone.utc).isoformat(), now + self.retention_seconds,
            ))
        return response_id, token

    def submit(self, request: FeedbackRequest) -> FeedbackReceipt:
        note, pii = redact_pii(request.note)
        payload = {"rating": request.rating, "categories": sorted(request.categories),
                   "note": note, "source_ids": sorted(request.source_ids)}
        payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            answer = db.execute("SELECT * FROM answers WHERE response_id = ?", (request.response_id,)).fetchone()
            token_hash = hashlib.sha256(request.feedback_token.encode()).hexdigest()
            if not answer or answer["expires_at"] <= time.time() or not secrets.compare_digest(answer["token_hash"], token_hash):
                raise FeedbackError("This answer is no longer available for feedback. Generate a new answer and try again.", 404)
            source_ids = {s["id"] for s in json.loads(answer["snapshot"]).get("sources", [])}
            if not set(request.source_ids) <= source_ids:
                raise FeedbackError("Feedback refers to a source that does not belong to this answer.")
            prior = db.execute("SELECT * FROM feedback_receipts WHERE submission_id = ?", (request.submission_id,)).fetchone()
            if prior:
                if prior["response_id"] != request.response_id or prior["payload_hash"] != payload_hash:
                    raise FeedbackError("This submission identifier was already used for different feedback.", 409)
                return FeedbackReceipt.model_validate_json(prior["receipt"])
            receipt = FeedbackReceipt(response_id=request.response_id, submission_id=request.submission_id,
                                      rating=request.rating, note_redacted=bool(pii))
            db.execute("""INSERT INTO feedback VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(response_id) DO UPDATE SET rating=excluded.rating,
                categories=excluded.categories, note=excluded.note,
                source_ids=excluded.source_ids, updated_at=excluded.updated_at""", (
                request.response_id, request.rating, json.dumps(payload["categories"]), note,
                json.dumps(payload["source_ids"]), datetime.now(timezone.utc).isoformat(),
            ))
            db.execute("INSERT INTO feedback_receipts VALUES (?, ?, ?, ?)", (
                request.submission_id, request.response_id, payload_hash, receipt.model_dump_json(),
            ))
            return receipt

    def summary(self) -> dict:
        """Read-only aggregate review data; no tokens, questions, or notes are returned."""
        if not self.path.exists():
            return {"reviewed_answers": 0, "by_model": [], "categories": {}}
        with closing(sqlite3.connect(f"{self.path.resolve().as_uri()}?mode=ro", uri=True)) as db:
            counts = db.execute("""SELECT a.model, f.rating, COUNT(*) FROM feedback f
                JOIN answers a USING(response_id) WHERE a.expires_at > ? GROUP BY a.model, f.rating""", (time.time(),)).fetchall()
            categories = {}
            for (raw,) in db.execute("SELECT f.categories FROM feedback f JOIN answers a USING(response_id) WHERE a.expires_at > ?", (time.time(),)):
                for category in json.loads(raw):
                    categories[category] = categories.get(category, 0) + 1
        return {"reviewed_answers": sum(row[2] for row in counts),
                "by_model": [{"model": model, "rating": rating, "count": count} for model, rating, count in counts],
                "categories": categories}
