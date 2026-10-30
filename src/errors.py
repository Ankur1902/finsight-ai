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


TRANSIENT_STATUS = {429, 500, 502, 503, 504}


def is_transient(exc: GenerationError) -> bool:
    return exc.status_code in TRANSIENT_STATUS and "configuration" not in str(exc)


def with_retries(call, *, attempts: int = 3, base_delay: float = 0.4, max_delay: float = 3.0, sleep=None):
    """Run `call` with bounded exponential backoff + jitter on transient
    provider failures. Auth/config errors and exhausted quotas are not retried
    beyond the attempt budget, and total delay is capped."""
    import random
    import time
    sleep = sleep or time.sleep
    for attempt in range(1, attempts + 1):
        try:
            return call()
        except GenerationError as exc:
            if attempt == attempts or not is_transient(exc):
                raise
            sleep(min(max_delay, base_delay * 2 ** (attempt - 1)) * (0.5 + random.random() / 2))
