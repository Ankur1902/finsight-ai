"""Safe errors at the provider boundary; never retain SDK response bodies."""
from __future__ import annotations


class GenerationError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def provider_error(provider: str, exc: Exception) -> GenerationError:
    """Classify failures using status metadata, never arbitrary exception text."""
    code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if code in (429, "429"):
        return GenerationError(
            f"{provider} is rate limited or its quota is exhausted. Check your provider quota before retrying.",
            status_code=429,
        )
    if code in (401, 403, 404, "401", "403", "404"):
        return GenerationError(
            f"{provider} configuration is unavailable. Check backend credentials and model access.",
            status_code=503,
        )
    if isinstance(exc, TimeoutError) or "timeout" in type(exc).__name__.lower() or code in (408, 504, "408", "504"):
        return GenerationError(
            f"{provider} timed out. Please retry; response times can vary.", status_code=504,
        )
    return GenerationError(f"{provider} could not complete the request. Please retry later.")
