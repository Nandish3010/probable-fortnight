"""Planner acceptance (harness/checklists/planner_agent.md) in stub mode: schema validity, trajectory,
loop termination, the policy-change beat, and the Cost Governor gate."""
import json
from pathlib import Path

import jsonschema
import pytest

from agents.gate.config import load_tenant
from agents.gate.models import Play
from agents.planner.run import run_planner_async
from agents.planner.tools import REQUIRED_ORDER
from harness.build_fixtures import EVAL_CRITERIA, TRACE_MARKER, evalset_from_trace
from harness.record_planner_traces import trace_facts

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "docs" / "schemas" / "play.schema.json").read_text())
V2 = (ROOT / "fixtures" / "policy_v2.txt").read_text()


def _run(store, gap_id, **kw):
    import asyncio

    for t in ("gaps", "plays", "products", "nodes", "customers", "affinity", "consent", "segments", "estimator_priors", "play_assignments", "inventory_batches", "inbound", "order_lines", "play_outcomes", "sense_runs", "policy"):
        store._materialise(t)
    if not (store.root / "manifest.json").exists():
        (store.root / "manifest.json").write_bytes((store.base.root / "manifest.json").read_bytes())
    return asyncio.run(run_planner_async(store.root, gap_id, **kw))


def _trajectory(events):
    return [e["function_call"]["name"] for e in events if e.get("function_call")]


def _is_subsequence(needle, hay):
    it = iter(hay)
    return all(any(x == n for x in it) for n in needle)


@pytest.mark.parametrize("gap_id", ["gap_chips_ds07", "gap_tea_ds04", "gap_cola_ds07", "gap_kaju_ds01", "gap_quinoa_out02"])
def test_planted_gap_yields_a_valid_play_within_three_iterations(sandbox, gap_id):
    out = _run(sandbox, gap_id)
    assert out["status"] == "proposed" and out["iterations"] <= 3
    play = out["play"]
    jsonschema.validate(play, SCHEMA, format_checker=jsonschema.FormatChecker())
    Play.model_validate(play)
    assert all(g["passed"] for g in play["guardrails"]) and len(play["guardrails"]) == 8
    assert _is_subsequence(REQUIRED_ORDER, _trajectory(out["events"]))
    assert play["cost"]["pct_of_rupees_at_stake"] <= load_tenant().thresholds["cost_ceiling_pct_of_rupees_at_stake"]


def test_chips_revises_after_margin_floor_failure(sandbox):
    out = _run(sandbox, "gap_chips_ds07")
    texts = [e["text"] for e in out["events"] if e.get("text")]
    assert any(t.startswith("Guardrail failed: margin_floor") for t in texts)
    assert out["iterations"] == 2 and out["play"]["mechanic"] == "bundle"
    assert out["play"]["alternatives"] and out["play"]["alternatives"][0]["mechanic"] == "coupon"


def test_policy_change_changes_the_tea_mechanic(sandbox):
    v1 = _run(sandbox, "gap_tea_ds04")
    v2 = _run(sandbox, "gap_tea_ds04", policy_text=V2, policy_version="v2")
    assert v1["play"]["mechanic"] == "transfer_plus_nudge"
    assert v2["play"]["mechanic"] != v1["play"]["mechanic"]
    assert v2["play"]["policy_version"] == "v2" and v2["play"]["play_id"].endswith("_v2")


def test_cost_governor_skips_small_gaps(sandbox):
    gaps = sandbox.read("gaps")
    small = next(g for g in gaps if g["rupees_at_stake"] < 500)
    out = _run(sandbox, small["gap_id"])
    assert out["status"] == "skipped" and out["play"] is None and out["events"][0]["author"] == "cost_governor"


def test_evalset_batch_schema_validity_and_gate_pass(sandbox):
    """50 largest eligible gaps: >= 95% valid plays after revision, loop <= 3 (checklist rows 1, 2, 5)."""
    gaps = [g for g in sandbox.read("gaps") if g["rupees_at_stake"] >= 500][:50]
    ok = 0
    for g in gaps:
        out = _run(sandbox, g["gap_id"])
        assert out["iterations"] <= 3
        if out["play"]:
            jsonschema.validate(out["play"], SCHEMA, format_checker=jsonschema.FormatChecker())
            ok += 1
    assert ok / len(gaps) >= 0.95, f"{ok}/{len(gaps)}"


def test_evalsets_committed():
    files = list((ROOT / "agents" / "planner" / "evalsets").glob("*.evalset.json"))
    assert len(files) >= 5
    for f in files:
        d = json.loads(f.read_text())
        data = d["eval_cases"][0]["conversation"][0]["intermediate_data"]
        names = [t["name"] for t in data["tool_uses"]]
        if TRACE_MARKER in d.get("description", ""):
            # recorded from a real run: whatever the model did, with one verdict per propose_play
            assert len(data["tool_responses"]) == names.count("propose_play")
        else:
            assert names[0] == "estimate_outcomes"


# ---------------------------------------------------------------- evalsets from recorded traces
# Evalsets built from recorded planner traces (harness/build_fixtures.py), the stub's replay mode
# (agents/planner/stub_llm.py, TAAL_STUB_TRAJECTORY=recorded) and the committed eval criteria.
# REAL_SHAPES are the tool-name sequences and propose_play verdicts of two real Gemini runs
# committed in eval/raw/planner_prompt_v6_2026-09-24/ (trace_gap_2e7621a152.jsonl,
# trace_gap_7bcc0cc853.jsonl); the rest of each synthetic trace is filled in by the stub.
REAL_SHAPES = {
    "gap_2e7621a152": (["estimate_outcomes", "propose_play", "check_guardrails", "estimate_outcomes", "check_guardrails", "propose_play", "propose_play"], [False, False, True]),
    "gap_7bcc0cc853": (["estimate_outcomes", "estimate_outcomes", "estimate_outcomes", "propose_play", "propose_play", "propose_play", "propose_play", "propose_play"], [False, False, False, False, True]),
}


def _records(gap_id: str, names: list[str], verdicts: list[bool], final_text: str) -> list[dict]:
    """A trace in harness/record_planner_traces.py's format with the given shape."""
    recs: list[dict] = [{"kind": "user", "content": {"role": "user", "parts": [{"text": f"Plan gap_id={gap_id} policy_version=v1"}]}}]
    v = iter(verdicts)
    for n in names:
        recs.append({"kind": "event", "event": {"author": "planner", "content": {"parts": [{"function_call": {"name": n, "args": {}}}]}, "usage_metadata": {"prompt_token_count": 100, "candidates_token_count": 10, "thoughts_token_count": 5}}})
        resp = {"valid": next(v), "errors": []} if n == "propose_play" else {}
        recs.append({"kind": "event", "event": {"author": "planner", "content": {"parts": [{"function_response": {"name": n, "response": resp}}]}}})
    recs.append({"kind": "event", "event": {"author": "planner", "content": {"parts": [{"text": final_text}]}}})
    if final_text:
        recs.append({"kind": "result", "status": "proposed", "planner_source": "model", "play": {"play_id": final_text.split()[-1]}})
    else:
        # the real no_play recordings (eval/raw/planner_traces_2026-09-28/): the model's own
        # conversation ends with no play and no text; run.py's deterministic fallback then
        # proposes one outside the model's turn, labelled planner_source=deterministic_fallback.
        recs.append({"kind": "result", "status": "no_play", "planner_source": "deterministic_fallback", "fallback_reason": "no_play after 0 iteration(s)", "play": None})
    return recs


def _summary() -> dict:
    return {"backend": "vertex", "model": "m", "prompt_version": "v6", "recorded_at": "2026-09-27T00:00:00Z"}


def test_evalset_from_trace_keeps_names_order_verdicts_and_the_exact_prompt():
    names, verdicts = REAL_SHAPES["gap_2e7621a152"]
    recs = _records("gap_2e7621a152", names, verdicts, "DONE play_2e7621a152_v1")
    es = evalset_from_trace("gap_2e7621a152", recs, _summary(), "eval/raw/x/gap_2e7621a152.jsonl")
    inv = es["eval_cases"][0]["conversation"][0]
    assert TRACE_MARKER in es["description"]
    assert [t["name"] for t in inv["intermediate_data"]["tool_uses"]] == names
    assert all(t["args"] == {} for t in inv["intermediate_data"]["tool_uses"])
    assert [r["response"]["valid"] for r in inv["intermediate_data"]["tool_responses"]] == verdicts
    assert inv["user_content"]["parts"][0]["text"] == "Plan gap_id=gap_2e7621a152 policy_version=v1"
    assert inv["final_response"]["parts"][0]["text"] == "DONE play_2e7621a152_v1"
    facts = trace_facts(recs)
    assert facts["revisions"] == 2 and facts["tokens"]["prompt"] == 700 and facts["tokens"]["model_calls"] == 7


def test_eval_criteria_are_not_zero_and_ignore_only_args():
    c = EVAL_CRITERIA["criteria"]
    assert c["tool_trajectory_avg_score"]["threshold"] >= 0.8
    assert c["tool_trajectory_avg_score"]["match_type"] == "EXACT" and c["tool_trajectory_avg_score"]["ignore_args"] is True
    assert c["response_match_score"] >= 0.8
    committed = ROOT / "agents" / "planner" / "evalsets" / "test_config.json"
    if committed.exists():
        assert json.loads(committed.read_text()) == EVAL_CRITERIA


@pytest.mark.parametrize("gap_id", sorted(REAL_SHAPES))
def test_stub_replay_reproduces_a_real_gemini_trajectory(sandbox, tmp_path, monkeypatch, gap_id):
    names, verdicts = REAL_SHAPES[gap_id]
    es = evalset_from_trace(gap_id, _records(gap_id, names, verdicts, f"DONE play_{gap_id[4:]}_v1"), _summary(), "x")
    (tmp_path / f"{gap_id}.evalset.json").write_text(json.dumps(es))
    monkeypatch.setenv("TAAL_STUB_TRAJECTORY", "recorded")
    monkeypatch.setenv("TAAL_STUB_TRAJECTORY_DIR", str(tmp_path))
    out = _run(sandbox, gap_id)
    assert _trajectory(out["events"]) == names
    got = [e["function_response"]["response"]["valid"] for e in out["events"] if (e.get("function_response") or {}).get("name") == "propose_play"]
    assert got == verdicts
    assert out["status"] == "proposed" and out["planner_source"] == "model"


def test_stub_replay_is_off_by_default(sandbox, tmp_path, monkeypatch):
    names, verdicts = REAL_SHAPES["gap_7bcc0cc853"]
    es = evalset_from_trace("gap_7bcc0cc853", _records("gap_7bcc0cc853", names, verdicts, "DONE play_7bcc0cc853_v1"), _summary(), "x")
    (tmp_path / "gap_7bcc0cc853.evalset.json").write_text(json.dumps(es))
    monkeypatch.delenv("TAAL_STUB_TRAJECTORY", raising=False)
    monkeypatch.setenv("TAAL_STUB_TRAJECTORY_DIR", str(tmp_path))
    out = _run(sandbox, "gap_7bcc0cc853")
    assert _trajectory(out["events"]) != names  # the scripted stub, not the recording


def test_stub_replay_reports_a_rejected_play_instead_of_the_recorded_done():
    """If the propose_play the recording accepted is rejected in replay, the stub must not end
    with the recorded "DONE <play_id>" (that would pass response_match on a run with no play)."""
    from agents.planner.stub_llm import StubPlannerLlm

    rec = {"tools": ["estimate_outcomes", "propose_play"], "verdicts": [True], "final_text": "DONE play_x_v1"}
    t = {"calls": [("estimate_outcomes", {}), ("propose_play", {})], "responses": [], "last": "response"}
    out = StubPlannerLlm()._replay(rec, t, {}, [], [], {}, {"propose_play": [{"valid": False}]})
    text = out.content.parts[0].text
    assert text.startswith("Replay diverged") and "DONE" not in text


@pytest.mark.parametrize("gap_id", ["gap_255b01502c", "gap_7bcc0cc853", "gap_8dec04ade8"])
def test_stub_replay_faithfully_reproduces_a_no_play_recording(sandbox, tmp_path, monkeypatch, gap_id):
    """These three 2026-09-28 recordings (eval/raw/planner_traces_2026-09-28/) are cases where the
    real model called estimate_outcomes once and then produced no propose_play and no closing text
    (MALFORMED_FUNCTION_CALL twice, per the raw trace) -- run.py's own deterministic fallback then
    proposes a play outside the model's conversation, but the recorded evalset's tool_names/
    final_text (what the model itself did) is exactly ["estimate_outcomes"] / "". The replay must
    stop there too, not fall through to a fabricated play: this is why adk eval's stub-with-replay
    run scores 47/50 rather than 50/50 on these three -- tool_trajectory_avg_score is 1.0 (exact
    match) but response_match_score is 0.0 because ADK's RougeEvaluator scores empty-vs-empty text
    as 0.0 fmeasure (see test_rouge1_of_empty_vs_empty_is_zero_not_the_replays_fault below), not
    because the replay diverges. There is no fix for this in the replay: never fabricate text the
    model did not say to chase a metric that cannot score silence as a match."""
    es = evalset_from_trace(gap_id, _records(gap_id, ["estimate_outcomes"], [], ""), _summary(), "x")
    (tmp_path / f"{gap_id}.evalset.json").write_text(json.dumps(es))
    monkeypatch.setenv("TAAL_STUB_TRAJECTORY", "recorded")
    monkeypatch.setenv("TAAL_STUB_TRAJECTORY_DIR", str(tmp_path))
    out = _run(sandbox, gap_id)
    assert _trajectory(out["events"]) == ["estimate_outcomes"]
    assert "propose_play" not in _trajectory(out["events"])
    # run.py's own deterministic fallback (never the model) is what proposes a play here, exactly
    # as it did in the real recording (eval/raw/planner_traces_2026-09-28/summary.json).
    assert out["status"] == "proposed" and out["planner_source"] == "deterministic_fallback"


def test_rouge1_of_empty_vs_empty_is_zero_not_the_replays_fault():
    """Documents the metric limitation behind the three FAILED response_match_score cases above:
    ADK's RougeEvaluator (google.adk.evaluation.final_response_match_v1) scores rouge1 fmeasure
    between the actual and expected final text. When the recorded (expected) text is empty --
    a genuine, faithfully-replayed "the model said nothing" outcome -- rouge1 fmeasure is 0.0 for
    any actual text, including a matching empty string. No change to stub_llm.py's replay can turn
    this into a passing score without either fabricating text the model never said (never done) or
    editing the evalset/criteria (also never done)."""
    pytest.importorskip("rouge_score", reason="google-adk[eval] extra; not in uv.lock, see harness/run_evals.py")
    from google.adk.dependencies.rouge_scorer import rouge_scorer

    scorer = rouge_scorer.RougeScorer(["rouge1"], use_stemmer=True)
    assert scorer.score("", "")["rouge1"].fmeasure == 0.0
    assert scorer.score("anything the stub could say instead", "")["rouge1"].fmeasure == 0.0
