"""Run the planner evalset with `adk eval` when it exists; otherwise print what would run.

Usage: python -m harness.run_evals [--dry-run]
Backend follows TAAL_MODEL_BACKEND (stub in CI; vertex needs GOOGLE_CLOUD_PROJECT).
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

from agents.gate.config import load_models
from harness.checklists import ROOT

AGENT_DIR = ROOT / "agents" / "planner"
EVALSETS = AGENT_DIR / "evalsets"
RESULTS = ROOT / "eval" / "runs" / "planner"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    models = load_models()
    backend = models["backend"]
    evalsets = sorted(EVALSETS.glob("*.evalset.json")) if EVALSETS.exists() else []
    cmd = ["adk", "eval", str(AGENT_DIR), *map(str, evalsets), "--print_detailed_results"]
    print(f"run_evals: backend={backend} model={models['ids']['flash']} evalsets={len(evalsets)}")
    if not evalsets:
        print(f"run_evals: {EVALSETS.relative_to(ROOT)} has no *.evalset.json yet; would run: {' '.join(cmd)}")
        return 0
    if backend == "vertex" and not os.environ.get(models["vertex"]["project_env"]):
        print("run_evals: vertex backend needs GOOGLE_CLOUD_PROJECT; nothing run")
        return 1
    if args.dry_run or shutil.which("adk") is None:
        print(f"run_evals: {'dry run' if args.dry_run else 'adk not on PATH'}; would run: {' '.join(cmd)}")
        return 0
    RESULTS.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    (RESULTS / "adk_eval.log").write_text(proc.stdout + proc.stderr, encoding="utf-8")
    print(proc.stdout[-2000:])
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
