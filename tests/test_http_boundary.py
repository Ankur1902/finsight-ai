import asyncio
import json

from src.http_boundary import BoundedJSONBody


def request(messages, *, max_bytes=8, content_type=b"application/json"):
    output, delivered = [], []

    async def app(_scope, receive, _send):
        delivered.append(await receive())

    async def receive():
        return messages.pop(0)

    async def send(message):
        output.append(message)

    scope = {"type": "http", "method": "POST", "headers": [(b"content-type", content_type)]}
    asyncio.run(BoundedJSONBody(app, max_bytes=max_bytes)(scope, receive, send))
    return output, delivered


def test_chunked_body_cannot_bypass_size_limit():
    output, delivered = request([
        {"type": "http.request", "body": b"12345", "more_body": True},
        {"type": "http.request", "body": b"6789", "more_body": False},
    ])
    assert output[0]["status"] == 413
    assert not delivered


def test_complete_json_body_is_replayed_once():
    output, delivered = request([{"type": "http.request", "body": b"{}", "more_body": False}])
    assert not output
    assert delivered == [{"type": "http.request", "body": b"{}", "more_body": False}]


def test_disconnect_stops_processing():
    assert request([{"type": "http.disconnect"}]) == ([], [])


def test_wrong_content_type_does_not_consume_body():
    output, delivered = request([], content_type=b"text/plain")
    assert output[0]["status"] == 415
    assert not delivered


def test_slow_upload_has_an_absolute_deadline():
    output = []

    async def app(*_args):
        raise AssertionError("A timed out body must not reach the app")

    async def receive():
        await asyncio.sleep(1)

    async def send(message):
        output.append(message)

    scope = {"type": "http", "method": "POST", "headers": [(b"content-type", b"application/json")]}
    asyncio.run(BoundedJSONBody(app, timeout_seconds=0.001)(scope, receive, send))
    assert output[0]["status"] == 408
    assert json.loads(output[-1]["body"])["detail"] == "Request body upload timed out."
