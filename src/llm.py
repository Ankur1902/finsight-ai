"""Pluggable local, Anthropic and Gemini generators.

Both expose `generate(system, user) -> str`.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Protocol

from .config import (
    ANTHROPIC_EFFORT,
    ANTHROPIC_MODEL,
    LLM_PROVIDER,
    LOCAL_LLM_MODEL,
    MAX_NEW_TOKENS,
    GEMINI_MODEL,
    GEMINI_THINKING_LEVEL,
    PROVIDER_TIMEOUT_MS,
)
from .errors import GenerationError, provider_error


class LLM(Protocol):
    name: str

    def generate(self, system: str, user: str, max_tokens: int | None = None) -> str: ...


class LocalLLM:
    """Runs fully offline. Uses the model's chat template and returns only the
    completion (the old HuggingFacePipeline wrapper echoed the whole prompt)."""

    def __init__(self, model_name: str = LOCAL_LLM_MODEL):
        import torch
        from transformers import pipeline

        self.name = f"local:{model_name}"
        # Checkpoint bfloat16 can be very slow on CPUs without native support.
        # CUDA retains the checkpoint's preferred precision; CPU uses float32.
        device = 0 if torch.cuda.is_available() else -1
        self._pipe = pipeline(
            "text-generation", model=model_name, device=device,
            dtype="auto" if device >= 0 else torch.float32,
        )

    def generate(self, system: str, user: str, max_tokens: int | None = None) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        out = self._pipe(
            messages,
            max_new_tokens=max_tokens or MAX_NEW_TOKENS,
            do_sample=False,  # deterministic; factual QA gains nothing from sampling
            repetition_penalty=1.05,
            return_full_text=False,
        )
        return out[0]["generated_text"].strip()


class AnthropicLLM:
    def __init__(self, model: str = ANTHROPIC_MODEL, effort: str = ANTHROPIC_EFFORT):
        import anthropic

        self.name = f"anthropic:{model}"
        self._model = model
        self._effort = effort
        self._client = anthropic.Anthropic(timeout=PROVIDER_TIMEOUT_MS / 1000, max_retries=0)

    def generate(self, system: str, user: str, max_tokens: int | None = None) -> str:
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens or MAX_NEW_TOKENS,
                system=system,
                output_config={"effort": self._effort},
                messages=[{"role": "user", "content": user}],
            )
        except Exception as exc:
            raise provider_error("Anthropic", exc) from None
        if response.stop_reason == "refusal":
            return "I can't help with that request."
        if response.stop_reason != "end_turn":
            raise GenerationError("Anthropic did not complete a usable answer")
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        if not text:
            raise GenerationError("Anthropic returned no answer")
        return text


def _resolve_provider() -> str:
    if LLM_PROVIDER != "auto":
        return LLM_PROVIDER
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    return "anthropic" if os.getenv("ANTHROPIC_API_KEY") else "local"


@lru_cache(maxsize=1)
def get_llm() -> LLM:
    provider = _resolve_provider()
    if provider == "anthropic":
        return AnthropicLLM()
    if provider == "local":
        return LocalLLM()
    if provider == "gemini":
        return GeminiLLM()
    raise ValueError(f"Unknown FINSIGHT_LLM_PROVIDER: {provider!r}")


class GeminiLLM:
    """Bounded Gemini calls; structured output still undergoes evidence validation."""
    def __init__(self, model: str = GEMINI_MODEL):
        from google import genai
        from google.genai import types
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("Set GEMINI_API_KEY in the backend environment")
        self.name = f"gemini:{model}"
        self._model = model
        self._types = types
        self._client = genai.Client(api_key=key, http_options=types.HttpOptions(
            timeout=PROVIDER_TIMEOUT_MS, retry_options=types.HttpRetryOptions(attempts=1)))

    def _generate(self, system, user, max_tokens, schema=None):
        options = {"system_instruction": system, "max_output_tokens": max_tokens,
                   "temperature": 0, "candidate_count": 1}
        if self._model.startswith("gemini-3"):
            options["thinking_config"] = self._types.ThinkingConfig(thinking_level=GEMINI_THINKING_LEVEL)
        elif self._model.startswith("gemini-2.5-flash"):
            options["thinking_config"] = self._types.ThinkingConfig(thinking_budget=0)
        if schema is not None:
            definition = schema.model_json_schema()
            definitions = definition.get("$defs", {})
            def compatible(value):
                if isinstance(value, dict):
                    if "$ref" in value:
                        return compatible(definitions[value["$ref"].rsplit("/", 1)[-1]])
                    if "anyOf" in value:
                        variants = value["anyOf"]
                        value = next((v for v in variants if v.get("type") == "number"), variants[0])
                    # Send the supported structural grammar. Pydantic independently
                    # enforces Decimal bounds, lengths, extra fields and provenance.
                    return {k: ({name: compatible(field) for name, field in v.items()}
                                if k == "properties" else compatible(v)) for k, v in value.items()
                            if k in {"type", "properties", "items", "required", "enum", "description"}}
                if isinstance(value, list):
                    return [compatible(v) for v in value]
                return value
            options.update(response_mime_type="application/json",
                           response_schema=compatible(definition))
        try:
            result = self._client.models.generate_content(model=self._model, contents=user,
                config=self._types.GenerateContentConfig(**options))
        except Exception as exc:
            raise provider_error("Gemini", exc) from None
        candidates = result.candidates or []
        if not candidates or str(candidates[0].finish_reason).split(".")[-1] != "STOP":
            raise GenerationError("Gemini did not complete a usable answer")
        text = result.text
        if not text or not text.strip():
            raise GenerationError("Gemini returned no answer")
        return text.strip()

    def generate(self, system, user, max_tokens=None):
        return self._generate(system, user, max_tokens or MAX_NEW_TOKENS)

    def generate_json(self, system, user, schema, max_tokens=4096):
        return self._generate(system, user, max_tokens, schema)
