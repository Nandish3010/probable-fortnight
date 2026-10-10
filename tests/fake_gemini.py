"""Offline stand-ins for Gemini so model failover can be tested without credentials or a network.

`FakeGemini` replaces the ADK `Gemini.generate_content_async` that agents/vertex_models.py's
delegates inherit, answering per model id; `FakeGenaiClient` replaces `google.genai.Client` for the
direct vision call; `pin_models` gives config/models.toml a distinct primary and fallback whatever
the committed file says. Same role as tests/fake_firestore.py.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from google import genai
from google.adk.models import LlmResponse
from google.adk.models.google_llm import Gemini
from google.genai import errors as genai_errors
from google.genai import types

PRIMARY = "gemini-3.5-flash"
FALLBACK = "gemini-3.1-flash-lite"


def api_error(code: int) -> genai_errors.APIError:
    """The error google-genai raises for an HTTP `code` (ClientError for 4xx, ServerError for 5xx)."""
    body = {"error": {"code": code, "message": f"simulated HTTP {code}", "status": "SIMULATED"}}
    return (genai_errors.ClientError if code < 500 else genai_errors.ServerError)(code, body)


def pin_models(monkeypatch, flash: str = PRIMARY, fallback: str | None = FALLBACK, **vertex) -> None:
    """Make load_models() report these ids (and extra [vertex] keys) for the rest of the test."""
    from agents.gate import config

    real = config._load

    def patched(path):
        d = real(path)
        if str(path).endswith("models.toml"):
            d["ids"] = {**d["ids"], "flash": flash, "fallback": fallback or ""}
            d["vertex"] = {**d["vertex"], **vertex}
        return d

    monkeypatch.setattr(config, "_load", patched)


def vertex_environment(monkeypatch) -> None:
    """Pre-set the variables vertex_env() would otherwise set for the whole process, so the
    monkeypatch fixture removes them again afterwards."""
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "asia-south1")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "taal-test-project")


def describe_thinking(tc: types.ThinkingConfig | None) -> str | None:
    if tc is None:
        return None
    if tc.thinking_level is not None:
        return f"level={str(getattr(tc.thinking_level, 'value', tc.thinking_level)).lower()}"
    return f"budget={tc.thinking_budget}"


class FakeGemini:
    """replies: model id -> an int HTTP status to raise, or the text to answer with."""

    def __init__(self, replies: dict[str, int | str]):
        self.replies = replies
        self.calls: list[tuple[str, str | None]] = []  # (model id, thinking config as sent)

    def install(self, monkeypatch) -> FakeGemini:
        fake = self

        async def generate_content_async(self_, llm_request, stream=False):
            config = llm_request.config
            fake.calls.append((llm_request.model, describe_thinking(config.thinking_config if config else None)))
            reply = fake.replies[llm_request.model]
            if isinstance(reply, int):
                raise api_error(reply)
            yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=reply)]))

        monkeypatch.setattr(Gemini, "generate_content_async", generate_content_async)
        return self

    @property
    def models_called(self) -> list[str]:
        return [m for m, _ in self.calls]


class FakeGenaiClient:
    """replies: model id -> an int HTTP status to raise, or a dict returned as the JSON text."""

    def __init__(self, replies: dict[str, int | dict[str, Any]]):
        self.replies = replies
        self.calls: list[dict[str, Any]] = []  # model, location, thinking

    def install(self, monkeypatch) -> FakeGenaiClient:
        fake = self

        def make_client(**kwargs):
            def generate_content(model, contents, config):
                fake.calls.append({"model": model, "location": kwargs.get("location"), "thinking": describe_thinking(config.thinking_config)})
                reply = fake.replies[model]
                if isinstance(reply, int):
                    raise api_error(reply)
                return SimpleNamespace(text=json.dumps(reply))

            return SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))

        monkeypatch.setattr(genai, "Client", make_client)
        return self

    @property
    def models_called(self) -> list[str]:
        return [c["model"] for c in self.calls]
