"""Bound JSON input before FastAPI parses it, including direct backend requests."""
import asyncio
from time import monotonic

from starlette.responses import JSONResponse


class BoundedJSONBody:
    def __init__(self, app, max_bytes=256 * 1024, timeout_seconds=15):
        self.app = app
        self.max_bytes = max_bytes
        self.timeout_seconds = timeout_seconds

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))

        async def reject(status, detail):
            await JSONResponse({"detail": detail}, status_code=status)(scope, receive, send)

        if headers.get(b"content-type", b"").split(b";", 1)[0].strip().lower() != b"application/json":
            return await reject(415, "Send a JSON request body.")
        try:
            declared = int(headers.get(b"content-length", b"0"))
            if declared < 0:
                raise ValueError
        except ValueError:
            return await reject(400, "Invalid request body length.")
        if declared > self.max_bytes:
            return await reject(413, "Request body exceeds the allowed size.")
        body = bytearray()
        deadline = monotonic() + self.timeout_seconds
        while True:
            remaining = deadline - monotonic()
            if remaining <= 0:
                return await reject(408, "Request body upload timed out.")
            try:
                message = await asyncio.wait_for(receive(), timeout=remaining)
            except TimeoutError:
                return await reject(408, "Request body upload timed out.")
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > self.max_bytes:
                return await reject(413, "Request body exceeds the allowed size.")
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, replay, send)
