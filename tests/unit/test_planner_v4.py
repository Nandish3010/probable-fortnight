"""Planner v4: fewer model turns (estimate_outcomes carries the gate verdict, propose_play takes a choice_index),
the tighter beats_markdown tolerance, and the failover order with a capped 429 backoff. No model call anywhere."""
import copy
import json

import pytest

from agents.gate import guardrails as gr
from agents.gate.config import load_tenant
from agents.planner import drafting
from agents.planner import tools as pt

GAPS = ("gap_tea_ds04", "gap_chips_ds07", "gap_cola_ds07", "gap_kaju_ds01", "gap_quinoa_out02")


@pytest.fixture
def planner(sandbox):
    """A planner context over a copy-on-write sandbox: propose_play writes plays, and the shared base tenant must not change."""
    from agents.planner.context import PlannerContext, reset_context, set_context

    for t in ("gaps", "plays", "products", "nodes", "customers", "affinity", "consent", "segments", "estimator_priors", "play_assignments", "inventory_batches", "inbound", "order_lines", "play_outcomes", "sense_runs", "policy"):
        sandbox._materialise(t)
    if not (sandbox.root / "manifest.json").exists():
        (sandbox.root / "manifest.json").write_bytes((sandbox.base.root / "manifest.json").read_bytes())
    c = PlannerContext.build(sandbox.root, run_id="t4")
    token = set_context(c)
    yield c
    reset_context(token)


class _State(dict):
    pass


class _TC:
    """The slice of ADK's ToolContext that propose_play touches."""

    def __init__(self):
        self.state = {}
        self.actions = type("A", (), {"escalate": False})()


def _drafts(c, gap_id, n=3):
    gap = pt.get_gap(gap_id)
    auds = pt.get_candidate_audiences(gap["sku"], [gap["node_id"]], drafting.OBJECTIVE_BY_GAP[gap["type"]], gap_id=gap_id)
    cands = drafting.candidate_mechanics(gap, c.policy_text)[:n]
    return gap, auds, [drafting.build_draft(gap, auds, cand, c.policy_version, "t4", 0.1, 20, ["en", "kn"], c.as_of.isoformat()) for cand in cands]


def test_required_order_and_prompt_no_longer_use_check_guardrails():
    from pathlib import Path

    assert pt.REQUIRED_ORDER == ["estimate_outcomes", "propose_play"]
    prompt = (Path(pt.__file__).parent / "prompts" / "planner.md").read_text(encoding="utf-8")
    assert "check_guardrails" not in prompt and "choice_index" in prompt


@pytest.mark.parametrize("gap_id", GAPS)
def test_estimate_outcomes_carries_the_same_verdict_check_guardrails_gives(planner, gap_id):
    _, _, drafts = _drafts(planner, gap_id)
    out = pt.estimate_outcomes(drafts)
    assert [r["choice_index"] for r in out] == list(range(len(drafts)))
    for d, r in zip(drafts, out, strict=True):
        chk = pt.check_guardrails(d)
        g = r["gate"]
        assert g["guardrails_all_passed"] == chk["all_passed"]
        assert [f["rule"] for f in g["failed_rules"]] == [x["rule"] for x in chk["results"] if not x["passed"]]
        if "beats_markdown" in chk:
            assert g["beats_markdown"] == chk["beats_markdown"]
            assert g["accepted_by_gate"] == chk["gate_passed"]
        else:
            assert g["accepted_by_gate"] == chk["all_passed"]
    assert any(r["gate"]["accepted_by_gate"] for r in out)


def test_a_draft_with_an_error_has_no_gate_and_the_rest_keep_their_index(planner):
    _, _, drafts = _drafts(planner, "gap_tea_ds04", 2)
    bad = {**copy.deepcopy(drafts[0]), "mechanic": "markdown", "mechanic_params": {}}
    out = pt.estimate_outcomes([bad, drafts[1]])
    assert "error" in out[0] and "gate" not in out[0]
    assert out[1]["choice_index"] == 1 and "gate" in out[1]
    play = pt.propose_play(choice_index=0, tool_context=_TC())
    assert play["valid"] is False and "usable: [1]" in play["errors"][0]


def test_beats_markdown_verdict_is_visible_before_proposing(planner, monkeypatch):
    """A draft far below the best markdown shows beats_markdown False in its gate, and propose_play by index says the same."""
    found = False
    for gap_id in GAPS:
        _, _, drafts = _drafts(planner, gap_id, 4)
        out = pt.estimate_outcomes(drafts)
        for r in out:
            if not r["gate"]["beats_markdown"]["passed"]:
                found = True
                tc = _TC()
                res = pt.propose_play(choice_index=r["choice_index"], tool_context=tc)
                assert res["valid"] is False and any(e.startswith("beats_markdown") for e in res["errors"])
                assert tc.state["guardrails_all_passed"] is False
    if not found:  # no demo draft is below its markdown: make the tolerance negative so that every play with a markdown reference is
        monkeypatch.setattr(gr, "beats_markdown_tolerance", lambda tenant, best: -1e9)
        for gap_id in GAPS:
            _, _, drafts = _drafts(planner, gap_id, 3)
            out = pt.estimate_outcomes(drafts)
            for d, r in zip(drafts, out, strict=True):
                if "alternatives" in out[0] and d["mechanic"] != "markdown" and "not applicable" not in r["gate"]["beats_markdown"]["detail"]:
                    assert r["gate"]["beats_markdown"]["passed"] is False and r["gate"]["accepted_by_gate"] is False
                    res = pt.propose_play(choice_index=r["choice_index"], tool_context=_TC())
                    assert res["valid"] is False and any(e.startswith("beats_markdown") for e in res["errors"])
                    found = True
    assert found


@pytest.mark.parametrize("gap_id", GAPS)
def test_propose_by_choice_index_writes_a_valid_model_chosen_play(planner, gap_id):
    gap, _, drafts = _drafts(planner, gap_id)
    out = pt.estimate_outcomes(drafts)
    ok = [r["choice_index"] for r in out if r["gate"]["accepted_by_gate"]]
    assert ok
    pick = ok[-1]  # the model's choice, not the first: code never picks
    tc = _TC()
    res = pt.propose_play(choice_index=pick, rationale="Chosen because the policy prefers it.", tool_context=tc)
    assert res["valid"] is True, res["errors"]
    assert tc.actions.escalate is True and tc.state["proposed_play_id"] == res["play_id"]
    row = planner.store.find("plays", play_id=res["play_id"])[-1]
    play = json.loads(row["play_json"])
    assert play["mechanic"] == drafts[pick]["mechanic"] and play["mechanic_params"].items() >= drafts[pick]["mechanic_params"].items()
    assert play["rationale"].endswith("Chosen because the policy prefers it.")
    assert len(play["guardrails"]) == 8 and all(g["passed"] for g in play["guardrails"])
    assert play["expected_outcome"]["margin_inr"] == out[pick]["expected_outcome"]["margin_inr"]
    assert len(play["alternatives"]) == min(3, len(drafts) - 1)


def test_choice_index_refers_to_the_latest_estimate_call(planner):
    _, _, drafts = _drafts(planner, "gap_tea_ds04", 2)
    pt.estimate_outcomes(drafts)
    pt.estimate_outcomes(drafts[1:])
    res = pt.propose_play(choice_index=1, tool_context=_TC())
    assert res["valid"] is False and "usable: [0]" in res["errors"][0]
    assert pt.propose_play(tool_context=_TC())["errors"][0].startswith("propose_play needs either choice_index")


def test_a_rationale_with_an_uncited_number_is_rejected_not_silently_kept(planner):
    _, _, drafts = _drafts(planner, "gap_tea_ds04", 2)
    out = pt.estimate_outcomes(drafts)
    pick = next(r["choice_index"] for r in out if r["gate"]["accepted_by_gate"])
    res = pt.propose_play(choice_index=pick, rationale="This also recovers 987654 rupees.", tool_context=_TC())
    assert res["valid"] is False and any("cite_or_drop" in e for e in res["errors"])


def test_a_minimal_draft_estimates_like_the_full_one(planner):
    gap, auds, drafts = _drafts(planner, "gap_tea_ds04", 1)
    full = drafts[0]
    minimal = {"gap_id": full["gap_id"], "mechanic": full["mechanic"], "mechanic_params": full["mechanic_params"], "audience": {"segment_ids": full["audience"]["segment_ids"]}}
    a, b = pt.estimate_outcomes([full])[0], pt.estimate_outcomes([minimal])[0]
    assert a["expected_outcome"] == b["expected_outcome"] and a["counterfactuals"] == b["counterfactuals"] and a["gate"] == b["gate"]
    res = pt.propose_play(choice_index=0, tool_context=_TC())
    assert res["valid"] is True, res["errors"]


def test_full_play_path_is_unchanged(planner):
    """The original path (the whole play object) still validates and writes exactly what finish_draft built: the stub and
    every recorded trace use it."""
    gap, auds, drafts = _drafts(planner, "gap_tea_ds04", 1)
    est = pt.estimate_outcomes(drafts)[0]
    full = drafting.finish_draft(drafts[0], gap, est, auds, [], planner.policy_text)
    full["guardrails"] = pt.check_guardrails(full)["results"]
    res = pt.propose_play(copy.deepcopy(full), _TC())
    assert res["valid"] is True, res["errors"]
    # the positional call shape the stub and the ADK loop use
    assert pt.propose_play(play=copy.deepcopy(full), tool_context=_TC())["valid"] is True


def test_tolerance_is_fifty_rupees_or_two_percent():
    t = load_tenant()
    assert gr.beats_markdown_tolerance(t, 1000.0) == 50.0
    assert gr.beats_markdown_tolerance(t, 10000.0) == 200.0
    assert gr.beats_markdown_tolerance(t, -10000.0) == 200.0
    assert t.markdown_setting("beats_tolerance_inr", None) == 50 and t.markdown_setting("beats_tolerance_pct", None) == 2.0


def test_a_play_below_the_best_legal_markdown_by_more_than_the_tolerance_is_sent_back():
    """A shallower markdown that is 50 to 500 rupees short of the best one passed the v3 tolerance (max(500, 5%)) and is
    sent back by max(50, 2%)."""
    import dataclasses

    from agents.gate.estimator import best_markdown, estimate, recovery_of
    from tests.unit.test_markdown_option import WIDGET, _gctx, _play, ctx

    c = ctx(product=WIDGET, audience=80)
    best = best_markdown(c)
    old = dataclasses.replace(load_tenant(), raw={**load_tenant().raw, "markdown": {**load_tenant().raw["markdown"], "beats_tolerance_inr": 500, "beats_tolerance_pct": 5.0}})
    hit = None
    for pct in range(11, 35):
        weak = _play(mechanic="markdown", mechanic_params={"markdown_pct": pct})
        est = estimate(weak, c)
        short = best["recovery_inr"] - recovery_of(est)
        if 60 < short < 400:
            hit = (weak, est, short)
            break
    assert hit, "no markdown depth lands 60 to 400 rupees below the best one on this fixture"
    weak, est, short = hit
    assert gr.check_beats_markdown(weak, est, _gctx(old), c)["passed"] is True  # v3's tolerance let it through
    assert gr.check_beats_markdown(weak, est, _gctx(), c)["passed"] is False  # v4's sends it back


# ------------------------------------------------------------------ failover order and the capped 429 backoff

def test_failover_chain_is_flash_regional_then_flash_global_then_lite(monkeypatch):
    from agents import vertex_models as vm
    from agents.gate.config import load_models

    m = load_models()
    chain = vm.failover_chain(m)
    assert chain == [(m["ids"]["flash"], None), (m["ids"]["flash"], "global"), (m["ids"]["fallback"], "global")]
    assert m["ids"]["flash"] == "gemini-3.5-flash" and m["ids"]["fallback"] == "gemini-3.5-flash-lite"
    off = {**m, "failover": {"primary_on_global": False}}
    assert vm.failover_chain(off) == [(m["ids"]["flash"], None), (m["ids"]["fallback"], "global")]


def test_a_429_is_retried_on_the_same_model_within_three_seconds_then_fails_over(monkeypatch):
    import asyncio

    from google.adk.models import LlmRequest, LlmResponse
    from google.adk.models.google_llm import Gemini
    from google.genai import types

    from agents import vertex_models as vm
    from tests.fake_gemini import api_error

    sleeps: list[float] = []

    async def fake_sleep(d):
        sleeps.append(d)

    monkeypatch.setattr(vm.asyncio, "sleep", fake_sleep)
    calls = {"n": 0}

    def make(fail_times):
        async def gen(self_, req, stream=False):
            calls["n"] += 1
            if calls["n"] <= fail_times:
                raise api_error(429)
            yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text="ok")]))

        return gen

    delegate = vm._delegate("gemini-3.5-flash", None)

    async def run():
        return [r async for r in delegate.generate_content_async(LlmRequest(model="gemini-3.5-flash", contents=[], config=types.GenerateContentConfig()))]

    monkeypatch.setattr(Gemini, "generate_content_async", make(2))
    out = asyncio.run(run())
    assert out[0].content.parts[0].text == "ok" and calls["n"] == 3 and len(sleeps) == 2 and sum(sleeps) <= 3.0
    # three 429s in a row: the error propagates (the FallbackModel then tries the next model), after at most 3 s of sleeping
    calls["n"], sleeps[:] = 0, []
    monkeypatch.setattr(Gemini, "generate_content_async", make(99))
    with pytest.raises(Exception) as err:
        asyncio.run(run())
    assert vm.status_of(err.value) == 429 and calls["n"] == 3 and sum(sleeps) <= 3.0
    # a non-429 error is never retried
    calls["n"], sleeps[:] = 0, []

    async def bad(self_, req, stream=False):
        calls["n"] += 1
        raise api_error(503)
        yield  # pragma: no cover

    monkeypatch.setattr(Gemini, "generate_content_async", bad)
    with pytest.raises(type(api_error(503))):
        asyncio.run(run())
    assert calls["n"] == 1 and sleeps == []


def test_a_full_429_walks_the_chain_in_order(monkeypatch):
    """The whole chain with a fake 429 on both flash endpoints: lite answers; the models called are flash, flash, lite."""
    from agents import vertex_models as vm
    from agents.customer.agent import build_customer_agent
    from tests.fake_gemini import FALLBACK, PRIMARY, pin_models, vertex_environment

    monkeypatch.setattr(vm, "LIVE_429_BACKOFF_S", ())
    pin_models(monkeypatch)
    vertex_environment(monkeypatch)
    agent = build_customer_agent({"chips": "SKU-1"}, backend="vertex")
    assert [m.model for m in agent.model.models] == [PRIMARY, PRIMARY, FALLBACK]


def test_estimate_shows_the_reach_a_segment_list_leaves_out(planner):
    gap, auds, drafts = _drafts(planner, "gap_tea_ds04", 1)
    full = copy.deepcopy(drafts[0])
    narrow = copy.deepcopy(drafts[0])
    narrow["audience"]["segment_ids"] = [auds[-1]["segment_id"]]
    a, b = pt.estimate_outcomes([full])[0], pt.estimate_outcomes([narrow])[0]
    assert a["reach"]["consented_customers_if_all_segments_included"] == b["reach"]["consented_customers_if_all_segments_included"]
    assert b["reach"]["consented_customers_in_this_draft"] < b["reach"]["consented_customers_if_all_segments_included"]
    md = pt.estimate_outcomes([{"gap_id": "gap_chips_ds07", "mechanic": "markdown", "mechanic_params": {"markdown_pct": 10}, "audience": {"segment_ids": ["all"]}}])[0]
    assert "reach" not in md  # a price cut contacts nobody


# Hashes taken from the v3 code (commit 76de6e2) with TAAL_NOW pinned: stub planner runs, which use the full-play path.
V3_GOLDEN = {
    "gap_chips_ds07": ("531c10154b83d13439f81fad26e430dfdc888188efae13b644993b8fc9f4b52d", "51456366c650ad7f2e4ee34dbf7a6ea4611138e6998a2becc5229c240dd32fe0", ["estimate_outcomes", "propose_play", "propose_play"], 2),
    "gap_cola_ds07": ("36df9cf10f81a0dc5eda1b932ae2d671d616fc0acf82ad719253937e280381b1", "f5b1c818f7f565b2e9d57ded9f66d2b96a831db25c14ceecf2d16de190bcf7bb", ["estimate_outcomes", "propose_play"], 1),
    "gap_kaju_ds01": ("ea019bc41f614a9e086547409008c67d2bb24ccadc7003ac4f5de202db46f5b3", "e47e7e51a00a455c6b41600983f3bd9261e8df9b92160d998e684caf919fb7ed", ["estimate_outcomes", "propose_play"], 1),
    "gap_quinoa_out02": ("7e57da81d59f3a10bcfe9e1934f58753ff0d4b0d5ec1d931c86a68f4bb2305df", "4d7c3ad1b15c7197f1da3a191dc3de5b33db34c996f490d4017658170ab9a91d", ["estimate_outcomes", "propose_play"], 1),
    "gap_tea_ds04": ("318c5e455bc2b6e0a6027e8e390ce71150707bd3910a96f2c3de0b0487e27f81", "216c91e062d645086eb03d6c53a173b7fbeb2f5a407aac2303a9836bbb0379ba", ["estimate_outcomes", "propose_play"], 1),
}
# The generated tenant differs by a float between Python 3.11 (CI) and 3.13 (kaju's blanket markdown: 1192.32 vs 1193.04),
# so kaju also has a 3.11 pair, taken from the same v3 code on 3.11-generated data.
V3_GOLDEN_ALT = {
    "gap_kaju_ds01": ("2f92c2ecef425c9bceb3ddc8918018afc0f65934976fbe92d95929b74aadbff3", "9afa78797d140cb824f7da229aebb8bb2aa45c56c1a977216e55a915b37917d2"),
}


def test_stub_runs_on_the_full_play_path_are_byte_identical_to_v3(sandbox, monkeypatch):
    """The stub (and so every recorded-trace replay) sends the whole play: same play JSON, same propose_play arguments, same
    tool sequence as the v3 code, byte for byte."""
    import hashlib

    from tests.agents.test_planner import _run

    monkeypatch.setenv("TAAL_NOW", "2026-09-12T03:30:00Z")

    def h(o):
        return hashlib.sha256(json.dumps(o, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    for gap_id, (play_hash, args_hash, tools, iterations) in V3_GOLDEN.items():
        out = _run(sandbox, gap_id)
        calls = [(e["function_call"]["name"], e["function_call"]["args"]) for e in out["events"] if e.get("function_call")]
        assert [c[0] for c in calls] == tools and out["iterations"] == iterations, gap_id
        got = (h(out["play"]), h([c[1] for c in calls if c[0] == "propose_play"]))
        assert got in {(play_hash, args_hash), V3_GOLDEN_ALT.get(gap_id)}, gap_id
