"""Run the planner evalsets with `adk eval` when they exist; otherwise print what would run.

Usage: python -m harness.run_evals [--dry-run] [--out eval/raw/adk_eval_<date>/<backend>]
Backend follows TAAL_MODEL_BACKEND (stub in CI; vertex needs GOOGLE_CLOUD_PROJECT).

- Criteria come from agents/planner/evalsets/test_config.json when it exists (harness/build_fixtures.py
  writes it next to evalsets built from recorded real-model traces), else ADK's default.
- The tools run against a throwaway copy-on-write sandbox of TAAL_DATA_DIR, so `propose_play`
  never writes plays into the base tenant.
- In stub mode, evalsets built from recorded traces switch the stub to replay the recorded
  trajectory (TAAL_STUB_TRAJECTORY=recorded, agents/planner/stub_llm.py) unless the caller set
  TAAL_STUB_TRAJECTORY explicitly.
- Per-evalset scores go to <out>/scores.json plus the adk log; the default <out> is
  eval/runs/planner/<backend>/ (gitignored). Pass --out eval/raw/... to commit a result.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from agents.gate.config import load_models
from harness.checklists import ROOT

AGENT_DIR = ROOT / "agents" / "planner"
EVALSETS = AGENT_DIR / "evalsets"
CONFIG = EVALSETS / "test_config.json"
HISTORY = AGENT_DIR / ".adk" / "eval_history"
RESULTS = ROOT / "eval" / "runs" / "planner"
TRACE_MARKER = "source=recorded_trace"
STATUS = {1: "PASSED", 2: "FAILED", 3: "NOT_EVALUATED"}


def _status(v) -> str:
    return STATUS.get(v, str(v)) if isinstance(v, int) else str(v)


def collect_scores(history: Path) -> list[dict]:
    rows = []
    for f in sorted(history.glob("*.evalset_result.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        if isinstance(d, str):  # adk writes the result JSON as a JSON string
            d = json.loads(d)
        for case in d["eval_case_results"]:
            rows.append({
                "eval_set_id": d["eval_set_id"],
                "status": _status(case["final_eval_status"]),
                "metrics": {m["metric_name"]: {"score": m.get("score"), "threshold": m.get("threshold"), "status": _status(m.get("eval_status"))} for m in case["overall_eval_metric_results"]},
            })
    return sorted(rows, key=lambda r: r["eval_set_id"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    models = load_models()
    backend = models["backend"]
    evalsets = sorted(EVALSETS.glob("*.evalset.json")) if EVALSETS.exists() else []
    cmd = ["adk", "eval", str(AGENT_DIR), *map(str, evalsets), "--print_detailed_results"]
    if CONFIG.exists():
        cmd += ["--config_file_path", str(CONFIG)]
    recorded = sum(1 for f in evalsets if TRACE_MARKER in json.loads(f.read_text(encoding="utf-8")).get("description", ""))
    print(f"run_evals: backend={backend} model={models['ids']['flash'] if backend == 'vertex' else 'stub-planner'} evalsets={len(evalsets)} (from recorded traces: {recorded}) criteria={CONFIG.relative_to(ROOT) if CONFIG.exists() else 'adk default'}")
    if not evalsets:
        print(f"run_evals: {EVALSETS.relative_to(ROOT)} has no *.evalset.json yet; would run: {' '.join(cmd)}")
        return 0
    if backend == "vertex" and not os.environ.get(models["vertex"]["project_env"]):
        print("run_evals: vertex backend needs GOOGLE_CLOUD_PROJECT; nothing run")
        return 1
    if args.dry_run or shutil.which("adk") is None:
        print(f"run_evals: {'dry run' if args.dry_run else 'adk not on PATH'}; would run: {' '.join(cmd)}")
        return 0

    from harness.record_planner_traces import sandbox

    out = Path(args.out) if args.out else RESULTS / backend
    out.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(HISTORY, ignore_errors=True)
    env = dict(os.environ)
    if backend == "stub" and recorded and "TAAL_STUB_TRAJECTORY" not in env:
        env["TAAL_STUB_TRAJECTORY"] = "recorded"
    base = Path(env.get("TAAL_DATA_DIR", ".local/data")).resolve()
    started = datetime.now(UTC)
    with tempfile.TemporaryDirectory(prefix="taal_eval_") as work:
        env["TAAL_DATA_DIR"] = str(sandbox(base, Path(work) / "tenant").root)
        proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, env=env)
    (out / "adk_eval.log").write_text(proc.stdout + proc.stderr, encoding="utf-8")
    rows = collect_scores(HISTORY)
    passed = sum(1 for r in rows if r["status"] == "PASSED")
    summary = {
        "ran_at": started.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "label": "measured" if backend == "vertex" else "stub (scripted stand-in, not the model)",
        "backend": backend,
        "model": models["ids"]["flash"] if backend == "vertex" else "stub-planner",
        "stub_trajectory": env.get("TAAL_STUB_TRAJECTORY", "") if backend == "stub" else None,
        "command": " ".join(["adk", "eval", "agents/planner", f"<{len(evalsets)} evalsets>", "--print_detailed_results"] + (["--config_file_path", str(CONFIG.relative_to(ROOT))] if CONFIG.exists() else [])),
        "criteria": json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else "adk default: tool_trajectory_avg_score 1.0 (EXACT, args compared), response_match_score 0.8",
        "evalsets": len(evalsets),
        "evalsets_from_recorded_traces": recorded,
        "scored": len(rows),
        "passed": passed,
        "adk_exit_code": proc.returncode,
        "results": rows,
    }
    (out / "scores.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"run_evals: {passed}/{len(rows)} evalsets passed ({len(evalsets)} run) -> {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}/scores.json")
    for r in rows:
        ms = ", ".join(f"{k}={v['score']}" for k, v in r["metrics"].items())
        print(f"  {r['status']:13s} {r['eval_set_id']:40s} {ms}")
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
