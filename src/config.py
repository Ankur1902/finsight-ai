"""Central configuration. Every knob can be overridden with an env var."""

from __future__ import annotations

import os
import math
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env", override=False)
DATA_DIR = ROOT_DIR / "data"
PERSIST_DIR = os.getenv("FINSIGHT_PERSIST_DIR", str(ROOT_DIR / "db"))
COLLECTION_NAME = "finsight"


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


def _integer(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(_env(name, str(default)))
    except ValueError:
        raise ValueError(f"{name} must be an integer") from None
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _choice(name: str, default: str, choices: set[str]) -> str:
    value = _env(name, default).strip().lower()
    if value not in choices:
        raise ValueError(f"{name} must be one of: {', '.join(sorted(choices))}")
    return value


# --- Models -----------------------------------------------------------------
EMBEDDING_MODEL = _env("FINSIGHT_EMBEDDING_MODEL", "BAAI/bge-m3")
RERANKER_MODEL = _env("FINSIGHT_RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")

# Auto prefers a configured Gemini key, then Anthropic, otherwise local.
LLM_PROVIDER = _choice("FINSIGHT_LLM_PROVIDER", "auto", {"auto", "local", "anthropic", "gemini"})
GEMINI_MODEL = _env("FINSIGHT_GEMINI_MODEL", "gemini-3.1-flash-lite")
GEMINI_THINKING_LEVEL = _choice("FINSIGHT_GEMINI_THINKING_LEVEL", "minimal", {"minimal", "low", "medium", "high"})
RETRIEVAL_MODE = _choice("FINSIGHT_RETRIEVAL_MODE", "auto", {"auto", "lexical", "hybrid"})
# 0.5B keeps CPU latency tolerable; Qwen/Qwen2.5-3B-Instruct cites far more reliably.
LOCAL_LLM_MODEL = _env("FINSIGHT_LOCAL_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")
ANTHROPIC_MODEL = _env("FINSIGHT_ANTHROPIC_MODEL", "claude-opus-5")
ANTHROPIC_EFFORT = _env("FINSIGHT_ANTHROPIC_EFFORT", "medium")
JUDGE_MODEL = _env("FINSIGHT_JUDGE_MODEL", "claude-sonnet-5")
MAX_NEW_TOKENS = _integer("FINSIGHT_MAX_NEW_TOKENS", 512, 64, 8192)
PROVIDER_TIMEOUT_MS = _integer("FINSIGHT_PROVIDER_TIMEOUT_MS", 15000, 1000, 120000)

# --- Retrieval --------------------------------------------------------------
CHUNK_SIZE = 512
CHUNK_OVERLAP = 100
RETRIEVER_K = _integer("FINSIGHT_K", 6, 1, 30)
FETCH_K = 30
RRF_K = 60  # standard reciprocal-rank-fusion constant

# Cross-encoder logit below which the best chunk is considered irrelevant and
# the system abstains instead of letting the LLM guess.
try:
    MIN_RERANK_SCORE = float(_env("FINSIGHT_MIN_RERANK_SCORE", "-4.0"))
except ValueError:
    raise ValueError("FINSIGHT_MIN_RERANK_SCORE must be a finite number") from None
if not math.isfinite(MIN_RERANK_SCORE):
    raise ValueError("FINSIGHT_MIN_RERANK_SCORE must be finite")

# --- Guardrails -------------------------------------------------------------
MAX_QUESTION_CHARS = 1000
