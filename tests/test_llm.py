from types import SimpleNamespace
import sys

import pytest

from src.llm import LocalLLM
from src.llm import AnthropicLLM
from src.llm import GeminiLLM


@pytest.mark.parametrize("cuda_available, expected_device, expected_dtype", [(False, -1, "float32"), (True, 0, "auto")])
def test_local_generator_selects_cpu_safe_precision(monkeypatch, cuda_available, expected_device, expected_dtype):
    seen = {}
    def factory(task, **kwargs):
        seen.update(kwargs)
        return lambda *_args, **_kwargs: [{"generated_text": "A cited answer [1]."}]
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: cuda_available), float32="float32"))
    monkeypatch.setitem(sys.modules, "transformers", SimpleNamespace(pipeline=factory))
    model = LocalLLM("test-model")
    assert seen["device"] == expected_device
    assert seen["dtype"] == expected_dtype
    assert model.generate("system", "question") == "A cited answer [1]."


def test_hosted_generator_honors_shared_output_budget(monkeypatch):
    requests = []
    def create(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="A cited answer [1].")])
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=lambda **_kwargs: client))
    monkeypatch.setattr("src.llm.MAX_NEW_TOKENS", 128)
    model = AnthropicLLM("test-model", effort="low")
    assert model.generate("system", "question") == "A cited answer [1]."
    assert requests[-1]["max_tokens"] == 128
    model.generate("system", "structured extraction", max_tokens=1800)
    assert requests[-1]["max_tokens"] == 1800


def test_gemini_keeps_key_server_side_and_handles_completion(monkeypatch):
    requests = []
    response = SimpleNamespace(candidates=[SimpleNamespace(finish_reason="STOP")], text="Revenue $65.6 billion [1].")
    def create(**kwargs):
        requests.append(kwargs)
        return response
    client = SimpleNamespace(models=SimpleNamespace(generate_content=create))
    types = SimpleNamespace(HttpOptions=lambda **kw: kw, HttpRetryOptions=lambda **kw: kw,
        ThinkingConfig=lambda **kw: kw, GenerateContentConfig=lambda **kw: kw)
    sdk = SimpleNamespace(types=types, Client=lambda **kw: client)
    monkeypatch.setitem(sys.modules, "google", SimpleNamespace(genai=sdk))
    monkeypatch.setitem(sys.modules, "google.genai", sdk)
    monkeypatch.setenv("GEMINI_API_KEY", "unit-test-key")
    monkeypatch.setattr("src.llm.GEMINI_THINKING_LEVEL", "minimal")
    model = GeminiLLM("gemini-3.1-flash-lite")
    assert model.generate("grounded system", "question", max_tokens=128).endswith("[1].")
    assert requests[-1]["config"]["max_output_tokens"] == 128
    assert requests[-1]["config"]["thinking_config"] == {"thinking_level": "minimal"}
    assert "unit-test-key" not in str(requests)
    class Schema:
        @staticmethod
        def model_json_schema():
            return {"type": "object", "additionalProperties": False,
                    "properties": {"facts": {"type": "array", "items": {"type": "object", "additionalProperties": False}}}}
    model.generate_json("system", "facts", Schema)
    assert "additionalProperties" not in str(requests[-1]["config"]["response_schema"])
    assert requests[-1]["config"]["response_schema"]["properties"]["facts"]["items"]["type"] == "object"
    assert requests[-1]["config"]["response_mime_type"] == "application/json"
    response.candidates[0].finish_reason = "MAX_TOKENS"
    with pytest.raises(RuntimeError, match="complete a usable"):
        model.generate("system", "question")


def test_gemini_rejects_missing_key_without_network(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    # Client creation must not occur with an absent credential.
    sdk = SimpleNamespace(types=SimpleNamespace())
    monkeypatch.setitem(sys.modules, "google", SimpleNamespace(genai=sdk))
    monkeypatch.setitem(sys.modules, "google.genai", sdk)
    with pytest.raises(RuntimeError, match="Set GEMINI_API_KEY"):
        GeminiLLM()
