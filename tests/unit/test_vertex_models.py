"""Model selection, failover and thinking-level mapping (agents/vertex_models.py). Offline: the
Gemini calls are replaced by tests/fake_gemini.py, so nothing here needs credentials."""
from __future__ import annotations

import asyncio

import pytest
from google.adk.models import FallbackModel, LlmRequest
from google.genai import types

from agents import vertex_models as vm
from agents.chat_runtime import chat_generate_config
from agents.planner.agent import _thinking_config
from tests.fake_gemini import (
    FALLBACK,
    PRIMARY,
    FakeGemini,
    FakeGenaiClient,
    api_error,
    vertex_environment,
)

MODELS = {
    "vertex": {"location": "asia-south1", "fallback_location": "global"},
    "ids": {"flash": PRIMARY, "fallback": FALLBACK},
    "thinking": {"planner_route": "low", "planner_final": "medium", "customer": "low"},
}


# ----------------------------------------------------------------------------- thinking levels


@pytest.mark.parametrize("level,expected", [("low", types.ThinkingLevel.LOW), ("medium", types.ThinkingLevel.MEDIUM), ("high", types.ThinkingLevel.HIGH)])
def test_gemini_3_takes_the_configured_level_as_thinking_level(level, expected):
    cfg = _thinking_config("gemini-3.5-flash", level)
    assert cfg.thinking_level == expected and cfg.thinking_budget is None


@pytest.mark.parametrize("level,budget", [("low", 0), ("medium", 1024), ("high", 4096)])
def test_gemini_2_5_takes_a_token_budget_never_a_level(level, budget):
    cfg = _thinking_config("gemini-2.5-flash", level)  # 2.5 answers thinking_level with 400 INVALID_ARGUMENT
    assert cfg.thinking_budget == budget and cfg.thinking_level is None


def test_chat_config_maps_the_customer_level_for_both_generations():
    three = chat_generate_config({"ids": {"flash": "gemini-3.5-flash"}, "thinking": {"customer": "low"}}, "customer", temperature=0.3)
    assert three.temperature == 0.3 and three.thinking_config.thinking_level == types.ThinkingLevel.LOW
    two = chat_generate_config({"ids": {"flash": "gemini-2.5-flash"}, "thinking": {"customer": "medium"}}, "customer", temperature=0.3)
    assert two.thinking_config.thinking_budget == 1024 and two.thinking_config.thinking_level is None


def test_an_unknown_level_never_reaches_the_api_as_a_400():
    assert _thinking_config("gemini-3.5-flash", "turbo").thinking_level == types.ThinkingLevel.LOW
    assert _thinking_config("gemini-2.5-flash", "turbo").thinking_budget == 1024  # the planner's old default
    assert chat_generate_config({"ids": {"flash": "gemini-2.5-flash"}, "thinking": {"customer": "turbo"}}, "customer", 0.3).thinking_config.thinking_budget == 0  # chat's old default


def test_a_per_model_level_remap_is_applied(monkeypatch):
    monkeypatch.setitem(vm.LEVEL_REMAP, "gemini-3.8-flash", {"minimal": "low"})  # 3.8 Flash answers "minimal" with 400
    assert vm.thinking_config("gemini-3.8-flash", "minimal").thinking_level == types.ThinkingLevel.LOW
    assert vm.thinking_config("gemini-3.5-flash", "minimal").thinking_level == types.ThinkingLevel.MINIMAL


# ----------------------------------------------------------------------------- what counts as an outage


@pytest.mark.parametrize("code", [404, 429, 500, 502, 503, 504])
def test_availability_statuses_fail_over(code):
    assert vm.failover_error(api_error(code)) and vm.status_of(api_error(code)) == code


@pytest.mark.parametrize("code", [400, 401, 403, 422])
def test_a_wrong_request_does_not_fail_over(code):
    assert not vm.failover_error(api_error(code))


def test_failover_sees_through_a_cause_chain_and_an_exception_group():
    try:
        try:
            raise api_error(503)
        except Exception as inner:
            raise RuntimeError("wrapped") from inner
    except RuntimeError as wrapped:
        assert vm.failover_error(wrapped)
    assert vm.failover_error(ExceptionGroup("tasks", [ValueError("x"), api_error(404)]))
    assert not vm.failover_error(ValueError("x"))
    assert not vm.failover_error(ExceptionGroup("tasks", [ValueError("x")]))


def test_model_unavailable_carries_what_the_api_answers_with():
    exc = vm.ModelUnavailable(PRIMARY, "both models returned 404")
    assert exc.model == PRIMARY and exc.retry_after_s == 30 and PRIMARY in str(exc)


# ----------------------------------------------------------------------------- which models


@pytest.mark.parametrize("ids,expected", [
    ({"flash": "a", "fallback": "b"}, ("a", "b")),
    ({"flash": "a", "fallback": "a"}, ("a", None)),  # retrying the same model is not a fallback
    ({"flash": "a", "fallback": ""}, ("a", None)),
    ({"flash": "a"}, ("a", None)),
])
def test_model_ids(ids, expected):
    assert vm.model_ids({"ids": ids}) == expected


def test_no_distinct_fallback_leaves_the_model_a_plain_id(monkeypatch):
    vertex_environment(monkeypatch)
    assert vm.vertex_model({"vertex": {}, "ids": {"flash": PRIMARY, "fallback": PRIMARY}}) == PRIMARY


def test_a_distinct_fallback_builds_a_fallback_model_with_its_own_location(monkeypatch):
    vertex_environment(monkeypatch)
    model = vm.vertex_model(MODELS)
    assert isinstance(model, FallbackModel) and model.model == PRIMARY
    primary, fallback = model.models
    assert (primary.model, fallback.model) == (PRIMARY, FALLBACK)
    assert primary.client_kwargs is None  # the primary follows GOOGLE_CLOUD_LOCATION (asia-south1)
    assert fallback.client_kwargs == {"location": "global"}  # the fallback is served only from the global endpoint
    assert 404 in model.retriable_status_codes  # ADK's own default set has no 404, which is what a retired id returns


# ----------------------------------------------------------------------------- the ADK FallbackModel path


def _request(level: str = "medium") -> LlmRequest:
    return LlmRequest(
        model=PRIMARY,
        contents=[types.Content(role="user", parts=[types.Part(text="hello")])],
        config=types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_level=level)),
    )


def _drain(model, request):
    async def run():
        return [r async for r in model.generate_content_async(request)]

    return asyncio.run(run())


def test_a_404_from_the_primary_is_answered_by_the_fallback(monkeypatch):
    vertex_environment(monkeypatch)
    fake = FakeGemini({PRIMARY: 404, FALLBACK: "from the fallback"}).install(monkeypatch)
    out = _drain(vm.vertex_model(MODELS), _request())
    assert out[0].content.parts[0].text == "from the fallback"
    assert fake.models_called == [PRIMARY, FALLBACK]


def test_the_primary_is_used_when_it_answers(monkeypatch):
    vertex_environment(monkeypatch)
    fake = FakeGemini({PRIMARY: "from the primary", FALLBACK: "from the fallback"}).install(monkeypatch)
    out = _drain(vm.vertex_model(MODELS), _request())
    assert out[0].content.parts[0].text == "from the primary" and fake.models_called == [PRIMARY]


def test_the_fallback_gets_the_thinking_config_its_own_generation_accepts(monkeypatch):
    vertex_environment(monkeypatch)
    models = {**MODELS, "ids": {"flash": PRIMARY, "fallback": "gemini-2.5-flash"}}  # a fallback from another generation
    fake = FakeGemini({PRIMARY: 503, "gemini-2.5-flash": "ok"}).install(monkeypatch)
    _drain(vm.vertex_model(models), _request("high"))
    assert fake.calls == [(PRIMARY, "level=high"), ("gemini-2.5-flash", "budget=4096")]


def test_a_wrong_request_is_not_retried_on_the_fallback(monkeypatch):
    vertex_environment(monkeypatch)
    fake = FakeGemini({PRIMARY: 400, FALLBACK: "never reached"}).install(monkeypatch)
    with pytest.raises(Exception) as err:
        _drain(vm.vertex_model(MODELS), _request())
    assert vm.status_of(err.value) == 400 and fake.models_called == [PRIMARY]


def test_when_both_fail_the_last_error_surfaces(monkeypatch):
    vertex_environment(monkeypatch)
    fake = FakeGemini({PRIMARY: 404, FALLBACK: 503}).install(monkeypatch)
    with pytest.raises(Exception) as err:
        _drain(vm.vertex_model(MODELS), _request())
    assert vm.status_of(err.value) == 503 and vm.failover_error(err.value)
    assert fake.models_called == [PRIMARY, FALLBACK]


# ----------------------------------------------------------------------------- the direct (vision) path

ROWS = {"rows": [{"sku_guess": "SKU-X", "sku_confidence": 0.9, "best_before_date": "2026-12-01", "date_confidence": 0.9, "facings_count": 4, "count_confidence": 0.9}]}
CONFIG = types.GenerateContentConfig(response_mime_type="application/json", temperature=0.0)


def test_generate_with_failover_retries_once_on_the_fallback_in_its_own_location(monkeypatch):
    vertex_environment(monkeypatch)
    fake = FakeGenaiClient({PRIMARY: 404, FALLBACK: ROWS}).install(monkeypatch)
    resp, used = vm.generate_with_failover(MODELS, ["photo", "prompt"], CONFIG)
    assert used == FALLBACK and resp.text and fake.models_called == [PRIMARY, FALLBACK]
    assert [c["location"] for c in fake.calls] == [None, "global"]  # primary: ambient asia-south1; fallback: global


def test_generate_with_failover_raises_model_unavailable_when_both_fail(monkeypatch):
    vertex_environment(monkeypatch)
    FakeGenaiClient({PRIMARY: 503, FALLBACK: 404}).install(monkeypatch)
    with pytest.raises(vm.ModelUnavailable) as err:
        vm.generate_with_failover(MODELS, ["photo", "prompt"], CONFIG)
    assert err.value.model == PRIMARY and err.value.retry_after_s == 30


def test_generate_with_failover_does_not_swallow_a_wrong_request(monkeypatch):
    vertex_environment(monkeypatch)
    fake = FakeGenaiClient({PRIMARY: 400, FALLBACK: ROWS}).install(monkeypatch)
    with pytest.raises(Exception) as err:
        vm.generate_with_failover(MODELS, ["photo", "prompt"], CONFIG)
    assert vm.status_of(err.value) == 400 and fake.models_called == [PRIMARY]


def test_a_second_pass_starts_on_the_model_that_answered_the_first(monkeypatch):
    vertex_environment(monkeypatch)
    fake = FakeGenaiClient({PRIMARY: 404, FALLBACK: ROWS}).install(monkeypatch)
    vm.generate_with_failover(MODELS, ["photo", "prompt"], CONFIG, start=FALLBACK)
    assert fake.models_called == [FALLBACK]


def test_the_vision_thinking_level_is_mapped_per_model(monkeypatch):
    vertex_environment(monkeypatch)
    fake = FakeGenaiClient({PRIMARY: 404, FALLBACK: ROWS}).install(monkeypatch)
    vm.generate_with_failover(MODELS, ["photo", "prompt"], CONFIG, thinking_level="low")
    assert [c["thinking"] for c in fake.calls] == ["level=low", "level=low"]
    assert CONFIG.thinking_config is None  # the shared config object is not mutated
