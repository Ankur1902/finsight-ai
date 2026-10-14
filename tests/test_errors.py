from types import SimpleNamespace

import pytest

from src.errors import provider_error


@pytest.mark.parametrize("code,status", [(429, 429), (401, 503), (403, 503), (404, 503), (504, 504), (500, 502)])
def test_provider_status_is_sanitized(code, status):
    error = provider_error("Gemini", SimpleNamespace(code=code, status_code=None))
    assert error.status_code == status
    assert "private-key" not in str(error)


def test_provider_exception_body_never_reaches_safe_error():
    error = provider_error("Gemini", RuntimeError("private-key and private request body"))
    assert "private" not in str(error)
    assert provider_error("Gemini", TimeoutError("private request body")).status_code == 504
