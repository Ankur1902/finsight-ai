"""Shared verification identity, independent of evaluation CLI imports."""
import hashlib
import json

from .config import (
    ROOT_DIR, MAX_NEW_TOKENS, GEMINI_THINKING_LEVEL, RETRIEVAL_MODE,
    RETRIEVER_K, PROVIDER_TIMEOUT_MS, MIN_RERANK_SCORE,
)
from .corpus import get_corpus
from .runtime import generator_identity


def configuration_fingerprint():
    pipeline_files = (
        "config.py", "llm.py", "errors.py", "rag.py", "chat.py", "prompts.py",
        "guardrails.py", "query_planner.py", "retrieval.py", "lexical_retriever.py",
        "hybrid_retriever.py", "ingest.py", "chunking.py", "embeddings.py", "vectorstore.py",
        "corpus.py", "runtime.py", "verification.py", "eval/verify_questions.py",
    )
    hashes = {name: hashlib.sha256((ROOT_DIR / "src" / name).read_bytes()).hexdigest()
              for name in pipeline_files}
    identity = ["verification-v3", get_corpus().fingerprint, generator_identity(),
                MAX_NEW_TOKENS, GEMINI_THINKING_LEVEL, RETRIEVAL_MODE,
                RETRIEVER_K, PROVIDER_TIMEOUT_MS, MIN_RERANK_SCORE, hashes]
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
