"""Classify why a failing `adk eval` evalset diverged from its recorded trajectory.

Reads agents/planner/.adk/eval_history/*.evalset_result.json (left behind by the most recent
`python -m harness.run_evals` invocation -- run this immediately after, before running evals
again) and, for every FAILED case, compares expected vs actual tool-name sequence into one of six
classes:
  (a) extra/fewer propose_play retries -- same tools other than propose_play count, propose_play
      count differs
  (b) extra/fewer estimate_outcomes or check_guardrails calls -- those counts differ, propose_play
      count the same
  (a+b) both of the above at once -- reported separately since collapsing it into either (a) or
      (b) alone would misstate which count changed
  (c) different tool order -- same multiset of tool names, different sequence
  (d) final response differs (no DONE, different play_id) -- tool sequence identical, only the
      final text differs
  (e) empty turns / no play -- actual sequence is empty or has no propose_play where expected did
  (f) other -- anything not covered above

Usage: uv run python -m harness.classify_eval_divergence --out eval/raw/adk_eval_<date>/vertex/divergence.json
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

HISTORY = Path(__file__).resolve().parent.parent / "agents" / "planner" / ".adk" / "eval_history"


def _tool_names(events: list[dict]) -> list[str]:
    names = []
    for ev in events:
        for part in ev.get("content", {}).get("parts") or []:
            fc = part.get("function_call")
            if fc:
                names.append(fc["name"])
    return names


def _final_text(inv: dict) -> str:
    return "".join(p.get("text", "") for p in (inv.get("final_response") or {}).get("parts") or [])


def classify(expected: list[str], actual: list[str], expected_text: str, actual_text: str) -> str:
    if not actual or ("propose_play" in expected and "propose_play" not in actual):
        return "empty_turns_or_no_play"
    if expected == actual:
        return "final_response_differs" if expected_text != actual_text else "no_divergence"
    if Counter(expected) == Counter(actual):
        return "different_tool_order"
    exp_pp, act_pp = expected.count("propose_play"), actual.count("propose_play")
    exp_other, act_other = Counter(t for t in expected if t != "propose_play"), Counter(t for t in actual if t != "propose_play")
    pp_differs, other_differs = exp_pp != act_pp, exp_other != act_other
    if pp_differs and other_differs:
        return "propose_play_retries_and_estimate_or_guardrail_counts_both_differ"
    if pp_differs:
        return "propose_play_retry_count_differs"
    if other_differs:
        return "estimate_or_guardrail_call_count_differs"
    return "other"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    rows = []
    for f in sorted(HISTORY.glob("*.evalset_result.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        if isinstance(d, str):
            d = json.loads(d)
        for case in d["eval_case_results"]:
            if case["final_eval_status"] == 1:  # PASSED
                continue
            inv = case["eval_metric_result_per_invocation"][0]
            actual_events = inv["actual_invocation"]["intermediate_data"]["invocation_events"]
            expected = [t["name"] for t in inv["expected_invocation"]["intermediate_data"].get("tool_uses") or []]
            actual = _tool_names(actual_events)
            expected_text = _final_text(inv["expected_invocation"])
            actual_text = _final_text(inv["actual_invocation"])
            cls = classify(expected, actual, expected_text, actual_text)
            rows.append({
                "eval_set_id": case["eval_set_id"],
                "class": cls,
                "expected_tools": expected,
                "actual_tools": actual,
                "expected_final_text": expected_text,
                "actual_final_text": actual_text,
                "metrics": {m["metric_name"]: m["score"] for m in case["overall_eval_metric_results"]},
            })

    counts = Counter(r["class"] for r in rows)
    out = {
        "failed_count": len(rows),
        "class_counts": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "rows": sorted(rows, key=lambda r: r["eval_set_id"]),
    }
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"classify_eval_divergence: {len(rows)} failing evalsets classified -> {args.out}")
    for cls, n in out["class_counts"].items():
        print(f"  {cls:38s} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
