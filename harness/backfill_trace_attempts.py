"""Add the per-attempt fields (`attempt`, full `rationale`, `rejections`) to a recorded planner
trace, from the run's raw ADK events.

A trace recorded before agents/planner/run.py grew those fields caps every string in a tool call at
400 characters, so a rejected rationale was cut off. The raw events (`adk_events.jsonl`, now a
release asset rather than a file in this repo) still hold the full text. Point `--raw` at a
directory laid out like the recording (`<raw>/run_0N/adk_events.jsonl`):

    uv run python -m harness.backfill_trace_attempts eval/raw/planner_real_traces_2026-09-28 \\
        --raw /path/to/extracted/eval/raw/planner_real_traces_2026-09-28

Only those three fields are added; every other field of every record is left as recorded. Where a
run has no raw events the fields that do not need them (`attempt`, `rejections`) are still added.
Idempotent.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from agents.planner.run import parse_rejections


def _full_rationales(adk_events: Path) -> dict[int, str]:
    """seq -> unshrunk rationale of each propose_play call. Event N after the leading `user` line is
    trace record seq N (seq 0 is the cost governor's own record)."""
    out: dict[int, str] = {}
    seq = 0
    for line in adk_events.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("kind") != "event":
            continue
        seq += 1
        for part in (row["event"].get("content") or {}).get("parts") or []:
            call = part.get("function_call")
            if call and call.get("name") == "propose_play":
                rationale = ((call.get("args") or {}).get("play") or {}).get("rationale")
                if rationale:
                    out[seq] = str(rationale)
    return out


def backfill_run(trace: Path, adk_events: Path | None = None) -> int:
    """Rewrite `trace` (a run's trace.jsonl) in place; returns the number of propose_play attempts."""
    full = _full_rationales(adk_events) if adk_events and adk_events.exists() else {}
    attempts = 0
    out: list[str] = []
    for line in trace.read_text(encoding="utf-8").splitlines():
        rec: dict[str, Any] = json.loads(line)
        name = (rec.get("function_call") or rec.get("function_response") or {}).get("name")
        if name == "propose_play":
            if "function_call" in rec:
                attempts += 1
                shown = (rec["function_call"].get("args") or {}).get("play", {}).get("rationale")
                if rec["seq"] in full:
                    rec["rationale"] = full[rec["seq"]]
                elif shown:
                    rec["rationale"] = shown
            else:
                resp = rec["function_response"].get("response") or {}
                if not resp.get("valid"):
                    rec["rejections"] = parse_rejections(resp.get("errors"))
            rec["attempt"] = attempts
        out.append(json.dumps(rec, ensure_ascii=False))
    trace.write_text("\n".join(out) + "\n", encoding="utf-8")
    return attempts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("recording", type=Path, help="committed recording directory holding run_0N/trace.jsonl")
    ap.add_argument("--raw", type=Path, default=None, help="directory holding run_0N/adk_events.jsonl (default: the recording itself)")
    args = ap.parse_args(argv)
    for run_dir in sorted(args.recording.glob("run_*")):
        if (run_dir / "trace.jsonl").exists():
            raw = (args.raw or args.recording) / run_dir.name / "adk_events.jsonl"
            print(f"{run_dir.name}: {backfill_run(run_dir / 'trace.jsonl', raw)} propose_play attempt(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
