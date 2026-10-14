"""Serialize shared local model access across HTTP research features."""
from threading import RLock
from contextlib import nullcontext

INFERENCE_LOCK = RLock()


def generator_identity() -> str:
    """Resolve model provenance without constructing or contacting a generator."""
    import os
    from .config import ANTHROPIC_MODEL, LLM_PROVIDER, LOCAL_LLM_MODEL, GEMINI_MODEL
    provider = LLM_PROVIDER
    if provider == "auto":
        provider = "gemini" if os.getenv("GEMINI_API_KEY") else "anthropic" if os.getenv("ANTHROPIC_API_KEY") else "local"
    if provider not in {"local", "anthropic", "gemini"}:
        raise RuntimeError("Unknown configured LLM provider")
    return f"{provider}:{ {'anthropic': ANTHROPIC_MODEL, 'local': LOCAL_LLM_MODEL, 'gemini': GEMINI_MODEL}[provider]}"


def inference_context():
    # CPU/GPU local models remain serialized. Remote chat does not wait behind analytics.
    return INFERENCE_LOCK if generator_identity().startswith("local:") else nullcontext()
