"""Which Gemini model a vertex-backend call uses, what happens when it fails, and how the configured
thinking levels map onto it. Every live call that reads `ids.flash` / `ids.fallback` from
config/models.toml goes through here.

Failover. `ids.flash` is the primary and `ids.fallback` a different model, verified separately.
A call the primary answers with 404 (an ID Vertex no longer serves, or does not serve in this
location), 429 (quota) or a 5xx is retried once on the fallback:

- chat and planner: ADK's `FallbackModel` wraps the two (agents/customer/agent.py,
  agents/planner/agent.py). The retry happens inside one model call, so a session never holds a
  half-finished turn and no agent is rebuilt per request.
- vision: a direct google-genai call, retried by `generate_with_failover`.

When both models fail the caller gets `ModelUnavailable`; the API turns it into a 503 with a
`model_unavailable` body (services/api/main.py). The planner instead falls back to its
deterministic draft (agents/planner/run.py).

Thinking. `[thinking]` in the config names a level ("low", "medium", "high"). Gemini 3 takes it as
`thinking_level`; Gemini 2.5 rejects that with 400 and takes a token budget instead.
`thinking_config` maps one to the other, and the delegates built here re-map the request for
whichever model actually serves it, so a fallback from another generation still gets a
configuration it accepts.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from google.adk.models import BaseLlm, FallbackModel, Gemini
from google.genai import errors as genai_errors
from google.genai import types

log = logging.getLogger(__name__)

RETRY_AFTER_S = 30

# Statuses that move a call from the primary to the fallback: ADK FallbackModel's own default set
# (429 quota, 500/502/503/504 server) plus 404, which is what Vertex answers for a model ID it has
# retired or does not serve in the configured location.
FAILOVER_STATUS_CODES = frozenset({404, 429, 500, 502, 503, 504})

# Token budgets for Gemini 2.5, which has no thinking_level. 0 turns thinking off on 2.5 Flash.
_BUDGET_BY_LEVEL = {"low": 0, "medium": 1024, "high": 4096}

# thinking_level values a Gemini 3 model accepts. A configured level outside this set is sent as
# "low" rather than failing the call with a 400.
_GEMINI3_LEVELS = ("minimal", "low", "medium", "high")

# Per-model exceptions, filled in from live verification: model id -> {configured level: level the
# model accepts}. Empty means every pinned model accepted every level in _GEMINI3_LEVELS.
LEVEL_REMAP: dict[str, dict[str, str]] = {}


class ModelUnavailable(RuntimeError):
    """The primary model and the fallback both failed with an availability error (404, 429, 5xx)."""

    def __init__(self, model: str, detail: str = "", retry_after_s: int = RETRY_AFTER_S):
        super().__init__(f"model {model} unavailable" + (f": {detail}" if detail else ""))
        self.model = model
        self.detail = detail
        self.retry_after_s = retry_after_s


def status_of(exc: BaseException | None, _depth: int = 0) -> int | None:
    """The HTTP status a google-genai error carries, looking through the exception chain and
    through exception groups (ADK runs model calls inside task groups)."""
    if exc is None or _depth > 6:
        return None
    if isinstance(exc, genai_errors.APIError):
        return exc.code
    if isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            code = status_of(sub, _depth + 1)
            if code is not None:
                return code
        return None
    return status_of(exc.__cause__ or exc.__context__, _depth + 1)


def failover_error(exc: BaseException) -> bool:
    """True when `exc` says the model could not serve the call (not that the call was wrong)."""
    return status_of(exc) in FAILOVER_STATUS_CODES


def vertex_env(models: dict[str, Any]) -> None:
    """Point google-genai at Vertex AI for the project/location in config/models.toml."""
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
    if models["vertex"].get("location") and not os.environ.get("GOOGLE_CLOUD_LOCATION"):
        os.environ["GOOGLE_CLOUD_LOCATION"] = models["vertex"]["location"]


def model_ids(models: dict[str, Any]) -> tuple[str, str | None]:
    """(primary, fallback). The fallback is None when none is configured or it is the primary
    itself: retrying the same model is not a fallback."""
    primary = models["ids"]["flash"]
    fallback = (models["ids"].get("fallback") or "").strip() or None
    return primary, (fallback if fallback != primary else None)


def _fallback_location(models: dict[str, Any]) -> str | None:
    """Set `[vertex].fallback_location` only when the fallback is served from a different
    location than the primary (e.g. the primary in asia-south1, the fallback on `global`)."""
    return models["vertex"].get("fallback_location") or None


def thinking_config(model_id: str, level: str, default_budget: int = 1024) -> types.ThinkingConfig | None:
    """The thinking configuration for `level` on `model_id`; None keeps the model's default."""
    try:
        if model_id.startswith("gemini-3"):
            sent = LEVEL_REMAP.get(model_id, {}).get(level, level)
            return types.ThinkingConfig(thinking_level=sent if sent in _GEMINI3_LEVELS else "low")  # type: ignore[arg-type]
        # Gemini 2.5 rejects thinking_level outright (400 INVALID_ARGUMENT); it takes a token budget.
        return types.ThinkingConfig(thinking_budget=_BUDGET_BY_LEVEL.get(level, default_budget))
    except Exception:  # older google-genai without ThinkingConfig: keep the default
        return None


def _level_of(config: types.ThinkingConfig) -> str | None:
    """The configured level behind a ThinkingConfig built for some other model."""
    if config.thinking_level is not None:
        name = getattr(config.thinking_level, "value", config.thinking_level)
        return str(name).lower()
    if config.thinking_budget is not None:
        budget = config.thinking_budget
        return "low" if budget <= 0 else "medium" if budget <= 1024 else "high"
    return None


class _AdaptedGemini(Gemini):
    """Gemini that re-maps the request's thinking configuration for its own model id before the
    call, so the same request can be served by a model from a different generation."""

    async def generate_content_async(self, llm_request, stream: bool = False):  # type: ignore[override]
        config = llm_request.config
        if config is not None and config.thinking_config is not None:
            level = _level_of(config.thinking_config)
            adapted = thinking_config(self.model, level) if level else None
            if adapted is not None:
                config.thinking_config = adapted
        async for response in super().generate_content_async(llm_request, stream):
            yield response


def _delegate(model_id: str, location: str | None) -> Gemini:
    return _AdaptedGemini(model=model_id, client_kwargs={"location": location} if location else None)


def vertex_model(models: dict[str, Any]) -> str | BaseLlm:
    """The `model=` for an ADK LlmAgent on the vertex backend: the primary alone when no distinct
    fallback is configured, else a FallbackModel over the primary and the fallback."""
    vertex_env(models)
    primary, fallback = model_ids(models)
    if fallback is None:
        return primary
    return FallbackModel(
        models=[_delegate(primary, None), _delegate(fallback, _fallback_location(models))],
        retriable_status_codes=FAILOVER_STATUS_CODES,
    )


def generate_with_failover(models: dict[str, Any], contents: Any, config: types.GenerateContentConfig, start: str | None = None, thinking_level: str | None = None):
    """One google-genai `generate_content` with the same failover as the agents: the primary, then
    the fallback on an availability error. Returns (response, model id that answered). `start` begins
    with that model (a second pass stays on the model that answered the first). Raises
    ModelUnavailable when every candidate failed with an availability error; any other error
    propagates unchanged."""
    from google import genai

    vertex_env(models)
    primary, fallback = model_ids(models)
    order = [primary] + ([fallback] if fallback else [])
    if start in order:
        order = [start] + [m for m in order if m != start]
    last: BaseException | None = None
    for model_id in order:
        location = _fallback_location(models) if model_id == fallback else None
        client = genai.Client(vertexai=True, location=location) if location else genai.Client(vertexai=True)
        call_config = config
        if thinking_level:
            call_config = config.model_copy(update={"thinking_config": thinking_config(model_id, thinking_level)})
        try:
            return client.models.generate_content(model=model_id, contents=contents, config=call_config), model_id
        except Exception as e:  # noqa: BLE001 -- narrowed right below
            if not failover_error(e):
                raise
            last = e
            log.warning("model %s failed with status %s; %s", model_id, status_of(e), "trying the fallback" if model_id != order[-1] else "no fallback left")
    raise ModelUnavailable(primary, detail=str(last)[:200]) from last

