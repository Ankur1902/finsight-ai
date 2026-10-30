"""HTTP hardening: per-client rate limiting and security headers."""
from __future__ import annotations

import os
import uuid
from collections import OrderedDict
from threading import Lock
from time import monotonic

from starlette.responses import JSONResponse

# Endpoints that call a paid model or heavy extraction.
EXPENSIVE_PATHS = {"/chat": (20, 60.0), "/changes": (10, 60.0), "/metrics": (10, 60.0), "/feedback": (30, 60.0),
                   "/guidance": (10, 60.0)}


class SlidingWindowLimiter:
    def __init__(self, max_clients: int = 4096):
        self.hits: OrderedDict[tuple[str, str], list[float]] = OrderedDict()
        self.max_clients = max_clients
        self.lock = Lock()

    def check(self, client: str, path: str, limit: int, window: float, now: float | None = None) -> float | None:
        """Return None if allowed, else seconds until the client may retry."""
        now = monotonic() if now is None else now
        key = (client, path)
        with self.lock:
            hits = [t for t in self.hits.get(key, []) if now - t < window]
            if len(hits) >= limit:
                self.hits[key] = hits
                return max(0.0, window - (now - hits[0]))
            hits.append(now)
            self.hits[key] = hits
            self.hits.move_to_end(key)
            while len(self.hits) > self.max_clients:
                self.hits.popitem(last=False)
        return None


class SecurityMiddleware:
    """Request id, rate limiting, optional API key, and defensive headers."""

    def __init__(self, app, limiter: SlidingWindowLimiter | None = None, limits=None):
        self.app, self.limiter, self.limits = app, limiter or SlidingWindowLimiter(), limits or EXPENSIVE_PATHS

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        request_id = uuid.uuid4().hex
        extra = [(b"x-request-id", request_id.encode()), (b"x-content-type-options", b"nosniff"),
                 (b"referrer-policy", b"no-referrer"), (b"cache-control", b"no-store"),
                 (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'")]

        async def reject(status, detail, more=()):
            response = JSONResponse({"detail": detail}, status_code=status, headers=dict(more))
            response.raw_headers.extend(extra)
            await response(scope, receive, send)

        # Optional shared secret between the Next.js proxy and the backend.
        required = os.getenv("FINSIGHT_API_KEY")
        path = scope["path"]
        if required and path != "/health":
            import hmac
            supplied = headers.get(b"x-api-key", b"").decode("latin-1")
            if not hmac.compare_digest(supplied, required):
                return await reject(401, "Authentication required.")

        limit = self.limits.get(path)
        if limit and scope["method"] != "OPTIONS":
            forwarded = headers.get(b"x-forwarded-for", b"").decode("latin-1").split(",")[0].strip()
            client = forwarded if os.getenv("FINSIGHT_TRUST_PROXY") and forwarded else (scope.get("client") or ("unknown",))[0]
            wait = self.limiter.check(client, path, *limit)
            if wait is not None:
                return await reject(429, "Too many requests. Please slow down and retry shortly.",
                                    [("retry-after", str(int(wait) + 1))])

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                names = {k.lower() for k, _ in message["headers"]}
                message["headers"] = list(message["headers"]) + [h for h in extra if h[0] not in names]
            await send(message)

        await self.app(scope, receive, send_with_headers)
