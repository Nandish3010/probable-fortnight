"""Model outage and failover through the real agents (chat, planner, vision) with the Gemini calls
faked (tests/fake_gemini.py): the fallback answers, a double failure is a structured outage, and the
planner falls back to its deterministic draft. No credentials, no network."""
from __future__ import annotations

import asyncio

import pytest
from google.adk.models import LlmResponse
from google.adk.models.google_llm import Gemini
from google.genai import types

from agents import vertex_models as vm
from agents.capture.vision import intake
from agents.customer.agent import build_customer_agent
from agents.customer.chat import reset_sessions, run_chat_async
from agents.gate.config import load_tenant
from agents.gate.store import OverlayStore
from agents.planner import agent as planner_agent
from agents.planner import run
from agents.planner.stub_llm import StubPlannerLlm
from tests.fake_gemini import (
    FALLBACK,
    PRIMARY,
    FakeGemini,
    FakeGenaiClient,
    api_error,
    pin_models,
    vertex_environment,
)

NOW = "2026-09-12T09:05:00Z"
ROWS = {"rows": [{"sku_guess": "SKU-MASALA-CHIPS-200G", "sku_confidence": 0.9, "best_before_date": None, "date_confidence": 0.4, "facings_count": 6, "count_confidence": 0.9}]}
BETTER = {"rows": [{**ROWS["rows"][0], "best_before_date": "2026-12-01", "date_confidence": 0.9}]}


@pytest.fixture
def vertex(monkeypatch):
    pin_models(monkeypatch)
    vertex_environment(monkeypatch)
    reset_sessions()


def _store(data_dir, tmp_path):
    return OverlayStore(data_dir, tmp_path / "sandbox" / "visitor-failover")


def _chat(store, backend="vertex"):
    return asyncio.run(run_chat_async(store, "CUST-MEENA:web", "Any offers?", now_iso=NOW, visitor_id="visitor-failover", backend=backend))


def test_chat_is_answered_by_the_fallback_when_the_primary_is_gone(vertex, data_dir, tmp_path, monkeypatch):
    fake = FakeGemini({PRIMARY: 404, FALLBACK: '{"text": "Hello from the fallback"}'}).install(monkeypatch)
    [env] = _chat(_store(data_dir, tmp_path))
    assert env["text"] == "Hello from the fallback"
    assert fake.models_called == [PRIMARY, FALLBACK]


def test_chat_with_both_models_down_is_model_unavailable(vertex, data_dir, tmp_path, monkeypatch):
    FakeGemini({PRIMARY: 503, FALLBACK: 429}).install(monkeypatch)
    with pytest.raises(vm.ModelUnavailable) as err:
        _chat(_store(data_dir, tmp_path))
    assert err.value.model == PRIMARY


def test_chat_does_not_hide_a_wrong_request(vertex, data_dir, tmp_path, monkeypatch):
    FakeGemini({PRIMARY: 400, FALLBACK: '{"text": "unreachable"}'}).install(monkeypatch)
    with pytest.raises(Exception) as err:
        _chat(_store(data_dir, tmp_path))
    assert not isinstance(err.value, vm.ModelUnavailable) and vm.status_of(err.value) == 400


def test_agents_get_a_fallback_model_and_the_mapped_thinking_config(vertex):
    agent = build_customer_agent({"chips": "SKU-1"}, backend="vertex")
    assert [m.model for m in agent.model.models] == [PRIMARY, FALLBACK]
    assert agent.generate_content_config.thinking_config.thinking_level == types.ThinkingLevel.LOW
    planner = planner_agent.build_planner(load_tenant(), "policy", "v1", "run-x", "2026-09-12", backend="vertex")
    assert [m.model for m in planner.sub_agents[0].model.models] == [PRIMARY, FALLBACK]


def test_vision_reads_on_the_fallback_and_reports_which_model_answered(vertex, base_store, monkeypatch):
    fake = FakeGenaiClient({PRIMARY: 404, FALLBACK: ROWS}).install(monkeypatch)
    res = intake(base_store, "DS-07", image_data_url="data:image/png;base64,AAAA", backend="vertex")
    assert res["model_id"] == FALLBACK
    assert fake.models_called == [PRIMARY, FALLBACK, FALLBACK]  # the second pass stays on the model that answered


def test_vision_with_both_models_down_is_model_unavailable(vertex, base_store, monkeypatch):
    FakeGenaiClient({PRIMARY: 404, FALLBACK: 500}).install(monkeypatch)
    with pytest.raises(vm.ModelUnavailable):
        intake(base_store, "DS-07", image_data_url="data:image/png;base64,AAAA", backend="vertex")


# ----------------------------------------------------------------------------- planner


def _run(store, gap_id="gap_tea_ds04", **kw):
    for t in ("gaps", "plays", "products", "nodes", "customers", "affinity", "consent", "segments", "estimator_priors", "play_assignments", "inventory_batches", "inbound", "order_lines", "play_outcomes", "sense_runs", "policy"):
        store._materialise(t)
    if not (store.root / "manifest.json").exists():
        (store.root / "manifest.json").write_bytes((store.base.root / "manifest.json").read_bytes())
    return asyncio.run(run.run_planner_async(store.root, gap_id, **kw))


def test_a_model_outage_makes_the_planner_fall_back_to_the_deterministic_draft(sandbox, monkeypatch):
    async def down(self, llm_request, stream=False):
        raise api_error(503)
        yield  # pragma: no cover

    monkeypatch.setattr(StubPlannerLlm, "generate_content_async", down)
    out = _run(sandbox)
    assert out["planner_source"] == "deterministic_fallback" and out["source"] == "deterministic_rules"
    assert out["fallback_reason"].startswith("model unavailable (HTTP 503)")


def test_a_wrong_request_still_fails_the_planner_run(sandbox, monkeypatch):
    async def bad(self, llm_request, stream=False):
        raise api_error(400)
        yield  # pragma: no cover

    monkeypatch.setattr(StubPlannerLlm, "generate_content_async", bad)
    with pytest.raises(Exception) as err:
        _run(sandbox)
    assert vm.status_of(err.value) == 400


def test_error_turns_are_counted_and_named_in_the_run_summary(sandbox, monkeypatch):
    async def empty(self, llm_request, stream=False):
        yield LlmResponse(error_code="MALFORMED_FUNCTION_CALL", error_message="the model returned nothing usable")

    monkeypatch.setattr(StubPlannerLlm, "generate_content_async", empty)
    out = _run(sandbox)
    assert out["planner_source"] == "deterministic_fallback"
    assert "returned an error (MALFORMED_FUNCTION_CALL)" in out["fallback_reason"]
    summary = next(e for e in out["events"] if e.get("kind") == "run_summary")
    assert summary["error_events"] >= 1
    assert any(e.get("error_code") == "MALFORMED_FUNCTION_CALL" for e in out["events"])


def test_after_an_empty_turn_the_next_request_is_low_thinking_and_nudged():
    health = planner_agent._TurnHealth()
    before = planner_agent._route_thinking_callback(PRIMARY, "low", "high", health)
    after = planner_agent._record_turn_callback(health)

    def request():
        return type("R", (), {"contents": [types.Content(role="user", parts=[types.Part(text="plan")])], "config": types.GenerateContentConfig()})()

    # a healthy first turn: nothing appended
    r1 = request()
    before(None, r1)
    assert len(r1.contents) == 1

    # the model returned nothing (ADK reports an error_code, no content): retry gets a nudge and low thinking
    after(None, LlmResponse(error_code="MALFORMED_FUNCTION_CALL"))
    assert health.last_turn_empty and health.empty_turns == 1
    r2 = request()
    before(None, r2)
    assert r2.contents[-1].parts[0].text == planner_agent.NUDGE
    assert r2.config.thinking_config.thinking_level == types.ThinkingLevel.LOW

    # a good turn clears it
    after(None, LlmResponse(content=types.Content(role="model", parts=[types.Part(text="DONE")])))
    r3 = request()
    before(None, r3)
    assert len(r3.contents) == 1 and not health.last_turn_empty


def test_an_empty_response_is_recognised():
    assert planner_agent.is_empty_response(LlmResponse())
    assert planner_agent.is_empty_response(LlmResponse(error_code="X", content=types.Content(role="model", parts=[types.Part(text="hi")])))
    assert not planner_agent.is_empty_response(LlmResponse(content=types.Content(role="model", parts=[types.Part(function_call=types.FunctionCall(name="propose_play", args={}))])))


_ = Gemini  # imported so a missing ADK class fails collection loudly
