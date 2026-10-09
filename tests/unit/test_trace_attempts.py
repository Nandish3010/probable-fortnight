"""Per-attempt fields on a planner trace: what the trace panel's "guardrail attempts" view reads
(web/components/traceAttempts.ts). Recorder side: agents/planner/run.py. Backfill side:
harness/backfill_trace_attempts.py, applied to the committed flagship recording."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents.planner import run
from harness import backfill_trace_attempts as bf

ROOT = Path(__file__).resolve().parents[2]
FLAGSHIP_RECORDING = ROOT / "eval" / "raw" / "planner_real_traces_2026-09-28" / "run_04" / "trace.jsonl"


@pytest.mark.parametrize("errors,expected", [
    (["guardrail cite_or_drop: uncited numbers in rationale: 52"], [("cite_or_drop", "uncited numbers in rationale: 52")]),
    (["guardrail margin_floor: net margin 1.96% vs snacks floor 8.00%", "guardrail frequency_cap: 3 plays"], [("margin_floor", "net margin 1.96% vs snacks floor 8.00%"), ("frequency_cap", "3 plays")]),
    (["runtime invariant: expected units off by 4"], [("runtime_invariant", "expected units off by 4")]),
    (["target lot is past its online sell-by: only outlet_markdown is allowed"], [("online_sellby", "target lot is past its online sell-by: only outlet_markdown is allowed")]),
    (["$: 'play_id' is a required property"], [("schema", "$: 'play_id' is a required property")]),
    (None, []),
])
def test_parse_rejections(errors, expected):
    assert [(g["guardrail"], g["reason"]) for g in run.parse_rejections(errors)] == expected


def test_stub_run_numbers_each_propose_play_attempt(sandbox):
    from tests.agents.test_planner_source import _run

    out = _run(sandbox, "gap_chips_ds07")
    propose = [e for e in out["events"] if (e.get("function_call") or e.get("function_response") or {}).get("name") == "propose_play"]
    calls = [e for e in propose if "function_call" in e]
    responses = [e for e in propose if "function_response" in e]
    assert len(calls) == len(responses) >= 2  # the scripted run is rejected once, then revised
    assert [e["attempt"] for e in calls] == list(range(1, len(calls) + 1))
    assert [e["attempt"] for e in responses] == [e["attempt"] for e in calls]
    for call in calls:  # the full text, where the args copy is cut at 400 characters
        assert call["rationale"].startswith(call["function_call"]["args"]["play"]["rationale"].removesuffix("..."))
    rejected = [e for e in responses if not e["function_response"]["response"]["valid"]]
    assert rejected and all(e["rejections"] and {"guardrail", "reason"} <= set(e["rejections"][0]) for e in rejected)
    assert "rejections" not in responses[-1]  # the accepted attempt carries none


def test_backfill_adds_attempt_fields_and_the_full_rationale(tmp_path):
    long_rationale = "r" * 900
    shrunk = long_rationale[:400] + "..."

    def call(seq, text):
        return {"seq": seq, "function_call": {"name": "propose_play", "args": {"play": {"rationale": text[:400] + "..." if len(text) > 400 else text}}}}

    def resp(seq, valid, errors):
        return {"seq": seq, "function_response": {"name": "propose_play", "response": {"valid": valid, "errors": errors}}}

    trace = tmp_path / "trace.jsonl"
    trace.write_text("\n".join(json.dumps(r) for r in [
        {"seq": 0, "text": "governor"},
        call(1, long_rationale), resp(2, False, ["guardrail cite_or_drop: uncited numbers in rationale: 7"]),
        call(3, "short"), resp(4, True, []),
        {"seq": 5, "kind": "run_summary"},
    ]) + "\n")
    adk = tmp_path / "adk_events.jsonl"
    adk.write_text("\n".join(json.dumps(r) for r in [
        {"kind": "user", "content": {}},
        {"kind": "event", "event": {"content": {"parts": [{"function_call": {"name": "propose_play", "args": {"play": {"rationale": long_rationale}}}}]}}},
        {"kind": "event", "event": {"content": {"parts": [{"function_response": {"name": "propose_play"}}]}}},
        {"kind": "event", "event": {"content": {"parts": [{"function_call": {"name": "propose_play", "args": {"play": {"rationale": "short"}}}}]}}},
    ]) + "\n")

    assert bf.backfill_run(trace, adk) == 2
    rows = [json.loads(line) for line in trace.read_text().splitlines()]
    assert [r.get("attempt") for r in rows] == [None, 1, 1, 2, 2, None]
    assert rows[1]["rationale"] == long_rationale and rows[1]["function_call"]["args"]["play"]["rationale"] == shrunk
    assert rows[2]["rejections"] == [{"guardrail": "cite_or_drop", "reason": "uncited numbers in rationale: 7"}]
    assert rows[3]["rationale"] == "short" and "rejections" not in rows[4]
    before = trace.read_text()
    assert bf.backfill_run(trace, adk) == 2 and trace.read_text() == before  # idempotent

    # no raw events: attempt numbers and rejections still land, the rationale stays as recorded
    bare = tmp_path / "bare.jsonl"
    bare.write_text("\n".join(json.dumps(r) for r in [call(1, long_rationale), resp(2, False, ["guardrail margin_floor: x"])]) + "\n")
    bf.backfill_run(bare)
    rows = [json.loads(line) for line in bare.read_text().splitlines()]
    assert rows[0]["rationale"] == shrunk and rows[1]["rejections"][0]["guardrail"] == "margin_floor"


def test_committed_flagship_recording_shows_every_rejected_attempt():
    rows = [json.loads(line) for line in FLAGSHIP_RECORDING.read_text(encoding="utf-8").splitlines()]
    calls = [r for r in rows if "function_call" in r and r["function_call"]["name"] == "propose_play"]
    responses = [r for r in rows if "function_response" in r and r["function_response"]["name"] == "propose_play"]
    assert [r["attempt"] for r in responses] == [1, 2, 3, 4]
    assert [bool(r["function_response"]["response"]["valid"]) for r in responses] == [False, False, False, True]
    for r in responses[:3]:
        assert [x["guardrail"] for x in r["rejections"]] == ["cite_or_drop"]
        assert r["rejections"][0]["reason"] == "uncited numbers in rationale: 52"
    assert all(c["rationale"] for c in calls)
    assert len(calls[0]["rationale"]) > 400  # backfilled from the raw events: not the 400-character cut
