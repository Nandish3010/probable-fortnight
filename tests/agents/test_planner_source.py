"""Provenance for a planner run: PLAN_SOURCES / resolve_source, the persisted play_json `source`,
the terminal `run_summary` trace record, and the deadline-triggered deterministic fallback path
(agents/planner/run.py). Same demo-tenant fixture as tests/agents/test_planner.py."""
from __future__ import annotations

import asyncio
import json
import time

import pytest

from agents.planner import run
from agents.planner.stub_llm import StubPlannerLlm


def _run(store, gap_id, **kw):
    for t in ("gaps", "plays", "products", "apparel_products", "apparel_stock", "style_requests", "nodes", "customers", "affinity", "consent", "segments", "estimator_priors", "play_assignments", "inventory_batches", "inbound", "order_lines", "play_outcomes", "sense_runs", "policy"):
        store._materialise(t)
    if not (store.root / "manifest.json").exists():
        (store.root / "manifest.json").write_bytes((store.base.root / "manifest.json").read_bytes())
    return asyncio.run(run.run_planner_async(store.root, gap_id, **kw))


# ----------------------------------------------------------------------------- resolve_source


def test_plan_sources_constant():
    assert run.PLAN_SOURCES == ("recorded_gemini", "scripted_stub", "deterministic_rules", "live_gemini")


@pytest.mark.parametrize("backend,planner_source,skipped,expected", [
    ("vertex", "model", False, "live_gemini"),                              # model-authored play, vertex backend
    ("stub", "model", False, "scripted_stub"),                              # model-authored play, stub backend
    ("vertex", "deterministic_fallback", False, "deterministic_rules"),     # fallback produced the play
    ("stub", "deterministic_fallback", False, "deterministic_rules"),
    ("vertex", None, True, "deterministic_rules"),                          # Cost Governor skipped the gap
    ("stub", None, True, "deterministic_rules"),
    ("vertex", "model", True, "deterministic_rules"),                       # skipped wins regardless of planner_source
])
def test_resolve_source_branches(backend, planner_source, skipped, expected):
    assert run.resolve_source(backend, planner_source, skipped) == expected


def test_resolve_source_no_play_uses_the_backends_model_source():
    """status `no_play`: the model path was attempted and the deterministic fallback also found no
    admissible mechanic, so `planner_source` stays "model" (run_planner_async only overwrites it to
    "deterministic_fallback" when the fallback actually produces a play). resolve_source cannot
    distinguish this from a model-authored play from its three inputs alone -- by construction it
    reports the backend's own model source either way, which is exactly what the spec asks for."""
    assert run.resolve_source("vertex", "model", False) == "live_gemini"
    assert run.resolve_source("stub", "model", False) == "scripted_stub"


# ----------------------------------------------------------------------------- normal stub run


def test_stub_run_sources_the_play_and_the_trace(sandbox):
    out = _run(sandbox, "gap_tea_ds04")
    assert out["status"] == "proposed" and out["source"] == "scripted_stub"
    assert out["play"]["source"] == "scripted_stub"
    row = sandbox.find("plays", play_id=out["play"]["play_id"])[-1]
    assert json.loads(row["play_json"])["source"] == "scripted_stub"
    last = out["events"][-1]
    assert last["kind"] == "run_summary" and last["source"] == "scripted_stub" and last["status"] == "proposed"
    assert last["author"] == "planner_run" and last["backend"] == "stub" and last["model"] == "stub-planner"
    assert last["play_id"] == out["play"]["play_id"]


def test_governor_skip_sources_the_trace_summary(sandbox):
    gaps = sandbox.read("gaps")
    small = next(g for g in gaps if g["rupees_at_stake"] < 500)
    out = _run(sandbox, small["gap_id"])
    assert out["status"] == "skipped" and out["source"] == "deterministic_rules"
    last = out["events"][-1]
    assert last["kind"] == "run_summary" and last["source"] == "deterministic_rules" and last["status"] == "skipped"


# ----------------------------------------------------------------------------- deadline fallback


def test_fallback_only_after_deadline_elapses(sandbox, monkeypatch):
    original_generate = StubPlannerLlm.generate_content_async

    async def delayed(self, llm_request, stream=False):
        await asyncio.sleep(1.0)
        async for resp in original_generate(self, llm_request, stream=stream):
            yield resp

    monkeypatch.setattr(StubPlannerLlm, "generate_content_async", delayed)

    calls: list[float] = []
    original_det = run.deterministic_plan

    def spy(ctx, gap_id):
        calls.append(time.monotonic())
        return original_det(ctx, gap_id)

    monkeypatch.setattr(run, "deterministic_plan", spy)

    t_start = time.monotonic()
    out = _run(sandbox, "gap_tea_ds04", deadline_s=0.3)

    assert out["source"] == "deterministic_rules"
    assert out["planner_source"] == "deterministic_fallback"
    assert out["fallback_reason"] is not None and "deadline exceeded after 0.3s" in out["fallback_reason"]
    assert out["elapsed_ms"] >= 300
    assert calls and calls[0] - t_start >= 0.3


def test_no_fallback_when_the_model_responds_in_time(sandbox, monkeypatch):
    calls: list[float] = []
    original_det = run.deterministic_plan

    def spy(ctx, gap_id):
        calls.append(time.monotonic())
        return original_det(ctx, gap_id)

    monkeypatch.setattr(run, "deterministic_plan", spy)

    out = _run(sandbox, "gap_tea_ds04")

    assert out["status"] == "proposed" and out["planner_source"] == "model"
    assert not calls


# ----------------------------------------------------------------------------- event_sink


def test_event_sink_receives_every_raw_adk_event(sandbox):
    seen = []
    out = _run(sandbox, "gap_tea_ds04", event_sink=seen.append)
    assert out["status"] == "proposed"
    assert len(seen) > 0
    assert all(hasattr(ev, "author") for ev in seen)
