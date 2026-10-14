"""How often the planner's first proposed play passes the gate, per model, from committed eval output.

The ADK trajectory metric (agents/planner/evalsets/test_config.json, EXACT) compares each live run
with a 28 Sep gemini-2.5-flash recording, retries included. A rejected `propose_play` is a play the
gate refused (schema, guardrails, money invariants: agents/planner/tools.py::propose_play), so the
retry count is itself a quality signal, and EXACT matching penalises a model for needing fewer.
This reports the signal directly, over the same 46 evalsets:

  first_attempt: the run called `propose_play` exactly once and ended "DONE <play_id>", i.e. its
  first play passed the gate.

Sources (all committed): the 46 recordings (agents/planner/evalsets/gap_*.evalset.json) and each
live run's per-case tool names (eval/raw/live_eval_<date>/adk_vertex/divergence.json lists every
failed case; a passed case's tools equal the recording's by definition of EXACT).

The gate changed between the 9 Oct and 12 Oct runs (f12da7f re-derives audience and estimate).
`--replay` checks that this is not what moved the number: it sends every `propose_play` payload
from the fully recorded gemini-2.5-flash runs (eval/raw/planner_real_traces_2026-09-28/) through
today's gate, dry (nothing is written), against the seeded tenant.

Usage: uv run python -m harness.first_attempt_acceptance --replay --out eval/raw/live_eval_2026-10-12/first_attempt.json
"""
from __future__ import annotations

import argparse
import copy
import json
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVALSETS = ROOT / "agents" / "planner" / "evalsets"
RUNS = {"2026-10-09": "gemini-2.5-flash", "2026-10-12": "gemini-3.5-flash"}
# The 28 Sep recordings the 9 and 12 Oct runs were scored against. The evalsets were re-recorded on
# 14 Oct 2026 (gemini-3.5-flash, prompt v7), so the old tool names live in this snapshot instead.
OLD_RECORDINGS = ROOT / "eval" / "raw" / "live_eval_2026-10-12" / "recordings_2026-09-28_tools.json"
REPLAY_TRACES = ROOT / "eval" / "raw" / "planner_real_traces_2026-09-28"


def recorded_tools(eval_set_id: str) -> tuple[list[str], str]:
    """(tool names, final text) of the recording behind one evalset."""
    d = json.loads((EVALSETS / f"{eval_set_id.removeprefix('planner_')}.evalset.json").read_text(encoding="utf-8"))
    names, final = [], ""
    for case in d["eval_cases"]:
        for inv in case["conversation"]:
            names += [t["name"] for t in (inv.get("intermediate_data") or {}).get("tool_uses", [])]
            final = " ".join(p.get("text") or "" for p in ((inv.get("final_response") or {}).get("parts") or [])).strip() or final
    return names, final


def first_attempt(tools: list[str], final_text: str) -> bool:
    return tools.count("propose_play") == 1 and (final_text or "").startswith("DONE ")


def _counts(cases: list[tuple[list[str], str]]) -> dict:
    attempts = [t.count("propose_play") for t, _ in cases]
    return {
        "cases": len(cases),
        "first_attempt": sum(first_attempt(t, f) for t, f in cases),
        "guardrails_checked_before_propose": sum("check_guardrails" in t and "propose_play" in t and t.index("check_guardrails") < t.index("propose_play") for t, _ in cases),
        "propose_play_calls_mean": round(sum(attempts) / len(attempts), 2),
    }


def _in_order(expected: list[str], actual: list[str]) -> bool:
    it = iter(actual)
    return all(t in it for t in expected)


def _any_order(expected: list[str], actual: list[str]) -> bool:
    from collections import Counter
    need, have = Counter(expected), Counter(actual)
    return all(have[t] >= n for t, n in need.items())


def posthoc(expected: list[tuple[list[str], str]], actual: list[tuple[list[str], str]]) -> dict:
    """Measures computed from stored results, not configured ADK metrics. IN_ORDER: every expected
    call appears in the run, in order, extras allowed. ANY_ORDER: every expected call appears, any
    order, extras allowed (counts respected)."""
    pairs = list(zip(expected, actual, strict=True))
    return {
        "cases": len(pairs),
        "exact": sum(e[0] == a[0] for e, a in pairs),
        "in_order": sum(_in_order(e[0], a[0]) for e, a in pairs),
        "any_order": sum(_any_order(e[0], a[0]) for e, a in pairs),
        "every_expected_tool_name_called": sum(set(e[0]) <= set(a[0]) for e, a in pairs),
        "ends_with_propose_play": sum(bool(a[0]) and a[0][-1] == "propose_play" for e, a in pairs),
    }


def _live_cases(raw: Path, day: str, ids: list[str], recorded) -> list[tuple[list[str], str]]:
    rows = {r["eval_set_id"]: r for r in json.loads((raw / f"live_eval_{day}" / "adk_vertex" / "divergence.json").read_text(encoding="utf-8"))["rows"]}
    return [(rows[i]["actual_tools"], rows[i]["actual_final_text"]) if i in rows else recorded(i) for i in ids]


def acceptance(raw: Path = ROOT / "eval" / "raw") -> dict:
    """The 9 and 12 Oct figures, against the 28 Sep recordings (from the committed snapshot)."""
    old = json.loads(OLD_RECORDINGS.read_text(encoding="utf-8"))["cases"]
    ids = sorted(old)

    def recorded(i: str) -> tuple[list[str], str]:
        return old[i]["tools"], old[i]["final"]

    out = {"evalsets": len(ids), "recordings_2026-09-28": {"model": "gemini-2.5-flash", **_counts([recorded(i) for i in ids])}}
    for day, model in RUNS.items():
        out[f"live_{day}"] = {"model": model, **_counts(_live_cases(raw, day, ids, recorded))}
    return out


def acceptance_rerecorded(day: str, model: str = "gemini-3.5-flash", raw: Path = ROOT / "eval" / "raw") -> dict:
    """The run of `day` scored against the evalsets as they are now (re-recorded 14 Oct 2026,
    gemini-3.5-flash, prompt v7). Both sides are the same model, so first-attempt acceptance of the
    recordings and of the verification run measures consistency, not accuracy."""
    ids = sorted(f"planner_{p.name.split('.')[0]}" for p in EVALSETS.glob("gap_*.evalset.json"))
    expected = [recorded_tools(i) for i in ids]
    actual = _live_cases(raw, day, ids, recorded_tools)
    return {
        "evalsets": len(ids),
        f"recordings_{day}": {"model": model, **_counts(expected)},
        f"live_{day}": {"model": model, **_counts(actual)},
        f"posthoc_{day}": posthoc(expected, actual),
    }


def replay(data_dir: str | Path, traces: Path = REPLAY_TRACES) -> list[dict]:
    """Every recorded propose_play payload, re-validated by today's gate. Dry: no store writes."""
    from agents.planner.context import PlannerContext, reset_context, set_context
    from agents.planner.tools import propose_play

    out = []
    for trace in sorted(traces.glob("run_*/trace.jsonl")):
        events = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines() if line.strip()]
        recorded = [e["function_response"]["response"]["valid"] for e in events if (e.get("function_response") or {}).get("name") == "propose_play"]
        today = []
        for e in events:
            call = e.get("function_call") or {}
            if call.get("name") != "propose_play":
                continue
            ctx = PlannerContext.build(data_dir, run_id="replay")
            ctx.store.upsert = lambda *a, **k: None
            token = set_context(ctx)
            try:
                tc = types.SimpleNamespace(state={}, actions=types.SimpleNamespace(escalate=False))
                r = propose_play(copy.deepcopy(call["args"]["play"]), tc)
            finally:
                reset_context(token)
            today.append({"valid": r["valid"], "errors": r["errors"]})
        out.append({"run": trace.parent.name, "recorded_valid": recorded, "today": today})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--replay", action="store_true")
    ap.add_argument("--data-dir", default=".local/data")
    ap.add_argument("--run-date", default=None, help="score eval/raw/live_eval_<date>/ against the current (re-recorded) evalsets instead of the 12 Oct set")
    a = ap.parse_args()
    out = acceptance_rerecorded(a.run_date) if a.run_date else acceptance()
    if a.replay:
        runs = replay(a.data_dir)
        out["replay_2026-09-28_through_todays_gate"] = {
            "source": str(REPLAY_TRACES.relative_to(ROOT)),
            "first_attempts_rejected_today": sum(not r["today"][0]["valid"] for r in runs),
            "runs": len(runs),
            "note": "first attempts only are data-independent where they fail on schema; later attempts cite numbers from the 28 Sep data, which has since been regenerated, so their verdicts today are not comparable",
            "detail": runs,
        }
    Path(a.out).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "replay_2026-09-28_through_todays_gate"}, indent=2))


if __name__ == "__main__":
    main()
