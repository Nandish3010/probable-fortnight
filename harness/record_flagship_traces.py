"""Record real planner runs for the flagship gap, N independent runs, into a self-contained
directory tree that harness/recorded_traces.py can later validate and seed into the flagship
gap's play.

    uv run python -m harness.record_flagship_traces --gap gap_chips_ds07 --runs 5 \\
        --out eval/raw/planner_real_traces_<YYYY-MM-DD>

Not to be confused with harness/record_planner_traces.py, a separate tool that records one run
per selected gap across many gaps to build ADK evalsets (harness/build_fixtures.py,
harness/run_evals.py) -- this one instead runs the SAME gap repeatedly to pick the best of several
independent attempts for the flagship's seeded play.

Refuses to run unless TAAL_MODEL_BACKEND=vertex (a real Gemini call is the entire point of this
tool), except with --allow-stub, which exists only to exercise this tool's own mechanics without
Vertex access. A stub run is never eligible for seeding regardless (harness/recorded_traces.py
requires backend "vertex" and source "live_gemini").

For each run this script: copies a tenant built fresh for the occasion (data.generator -> Sense,
deliberately never harness.seed_plays -- see build_base_tenant) into its own scratch directory, so
no run ever sees a play another run of this same invocation produced; runs the planner against
that copy; and writes <out>/run_0N/{trace.jsonl, adk_events.jsonl, play.json, result.json}. It then
writes <out>/flagship_gap.json (the gap context the planner received) and <out>/summary.json (every
number in it recomputed from the per-run files just written, never carried over from an in-loop
variable). Everything is scanned for credential- or PII-shaped strings before any of it is written.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

from agents.gate.config import ROOT, load_models
from agents.planner import tools as pt
from agents.planner.context import PlannerContext, reset_context, set_context
from agents.planner.drafting import OBJECTIVE_BY_GAP
from agents.planner.run import DEFAULT_DEADLINE_S, run_planner_async

DEFAULT_TENANT_CONFIG = "config/tenant.demo.toml"
DEFAULT_TAAL_NOW = "2026-09-12T03:30:00Z"
GENERATOR_SEED = 20260912
PROMPTS_DIR = ROOT / "agents" / "planner" / "prompts"


class RecorderAbort(Exception):
    """An expected, clearly-explained refusal (wrong backend, missing credentials, an unknown gap,
    sensitive-looking content) -- caught once in main() and printed as one line, not a traceback."""


# ------------------------------------------------------------------------- sensitive-content scan
#
# A safety net, not the primary defence (this tenant is synthetic and has no email/phone fields to
# begin with -- verified by inspection of data/generator). Reports which file and what kind of
# finding, never the matched text: the abort message must not itself leak the thing it refuses to
# write.

_SENSITIVE_PATTERNS = {
    "private key marker": re.compile(r"BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY"),
    "private_key field": re.compile(r'"private_key"\s*:'),
    "google OAuth2 access token": re.compile(r"\bya29\.[\w.-]+"),
    "google API key": re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"),
    "service account json": re.compile(r'"type"\s*:\s*"service_account"'),
    "email address": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
}
# A whole token (split on anything but word characters and hyphens, so a JSON id/run_id/UUID like
# "adk-8bfa2e71-1474-4742-a189-9993..." is ONE token, not a lucky all-digit sub-run of it) that is
# itself nothing but digits, hyphens and an optional leading "+", at least 9 digits long. A bare ISO
# date ("YYYY-MM-DD") is excluded explicitly, rather than aborting every recording on its own
# started_at/finished_at/deadline_date/TAAL_NOW fields; a bare, unpunctuated run of digits (an id, a
# count, or -- constantly, in every trace -- a Unix timestamp's whole-second part) is not treated as
# phone-shaped either, since this tenant plants no phone field at all (verified: data/generator) and
# a real one would almost always carry a "+", a space or a hyphen.
_TOKEN_RE = re.compile(r"[+\w-]+")
_ISO_DATE_RE = re.compile(r"^(19|20)\d{2}-\d{2}-\d{2}$")


def _looks_like_phone(token: str) -> bool:
    if _ISO_DATE_RE.match(token) or not re.fullmatch(r"\+?[\d-]{9,20}", token):
        return False
    digits = token.replace("-", "").lstrip("+")
    return 9 <= len(digits) <= 15 and (token.startswith("+") or "-" in token[1:])


def _scan_or_abort(outputs: dict[str, str]) -> None:
    findings: list[str] = []
    for path, content in outputs.items():
        for name, pat in _SENSITIVE_PATTERNS.items():
            if pat.search(content):
                findings.append(f"{path}: possible {name}")
        if any(_looks_like_phone(tok) for tok in _TOKEN_RE.findall(content)):
            findings.append(f"{path}: possible phone number")
    if findings:
        raise RecorderAbort("refusing to write -- sensitive-looking content found:\n" + "\n".join(f"  {f}" for f in findings))


# ------------------------------------------------------------------------------ backend / tenant

def _resolve_backend(allow_stub: bool) -> str:
    backend = load_models()["backend"]
    if backend == "vertex":
        creds = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if not creds:
            raise RecorderAbort("TAAL_MODEL_BACKEND=vertex but GOOGLE_APPLICATION_CREDENTIALS is unset -- a real Vertex call needs credentials.")
        if not Path(creds).exists():
            raise RecorderAbort(f"GOOGLE_APPLICATION_CREDENTIALS={creds!r} does not point to an existing file.")
        return backend
    if allow_stub and backend == "stub":
        return backend
    raise RecorderAbort(f"TAAL_MODEL_BACKEND={backend!r}, not 'vertex' -- refusing to record a real planner trace. Pass --allow-stub only to test this tool's own mechanics; a stub run is never eligible for seeding (harness/recorded_traces.py).")


def _run_subprocess(args: list[str], env: dict[str, str]) -> None:
    proc = subprocess.run(args, env=env, cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RecorderAbort(f"{' '.join(args)} failed (exit {proc.returncode}):\n{proc.stdout}\n{proc.stderr}")


def build_base_tenant(base_dir: Path, tenant_config: str, taal_now: str) -> None:
    """Fresh tenant -> Sense, as subprocesses under the Makefile's own env (`make generate`'s first
    two steps) -- deliberately never harness.seed_plays. seed_plays plans every demo gap, the
    flagship first, before this script would get its own turn at it; a run recorded against that
    state would see past plays and an audience history a real first-time planner run for the
    flagship never actually sees. Subprocesses (not calling generate()/run_sense() in-process) so
    this always matches what `make generate` itself does, with no shared module state carried over
    from this process (e.g. an already-loaded tenant config)."""
    env = {**os.environ, "TAAL_DATA_DIR": str(base_dir), "TAAL_TENANT_CONFIG": tenant_config, "TAAL_NOW": taal_now}
    _run_subprocess([sys.executable, "-m", "data.generator", "--out", str(base_dir), "--seed", str(GENERATOR_SEED)], env)
    _run_subprocess([sys.executable, "-m", "jobs.sense", "--data", str(base_dir)], env)


def prepare_base_tenant(base_data: str | None, work_root: Path, tenant_config: str, taal_now: str) -> Path:
    """The base tenant every run copies from. --base-data reuses one already built this way (its
    manifest.json + gaps.jsonl existing is the only check -- the caller is responsible for it
    having been built via data.generator + jobs.sense, not harness.seed_plays); otherwise it is
    built once into that path (so a second invocation with the same --base-data reuses it too), or
    into `work_root` when no --base-data was given at all. Never written to afterward -- every run
    only ever touches its own copy under `work_root`."""
    if base_data:
        base_dir = Path(base_data)
        if (base_dir / "manifest.json").exists() and (base_dir / "gaps.jsonl").exists():
            return base_dir
        base_dir.mkdir(parents=True, exist_ok=True)
    else:
        base_dir = work_root / "base"
    build_base_tenant(base_dir, tenant_config, taal_now)
    return base_dir


def _gap_context(base_dir: Path, gap_id: str) -> dict[str, Any]:
    """The context the planner is actually handed for this gap (agents.planner.tools.get_gap and
    get_candidate_audiences -- the same two calls run.py's own _context_block makes), computed
    read-only against the base tenant so it reflects exactly what every run below will see before
    it makes its own copy."""
    ctx = PlannerContext.build(base_dir, run_id="record-planner-traces-context")
    token = set_context(ctx)
    try:
        try:
            gap = pt.get_gap(gap_id)
        except KeyError as e:
            raise RecorderAbort(f"unknown gap {e}") from e
        audiences = pt.get_candidate_audiences(gap["sku"], [gap["node_id"]], OBJECTIVE_BY_GAP[gap["type"]], gap_id=gap_id)
    finally:
        reset_context(token)
    return {"gap_id": gap_id, "gap": gap, "candidate_audiences": audiences}


# ------------------------------------------------------------------------------------- per run

def _dump(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json", exclude_none=True)
    return obj


async def _run_once(base_dir: Path, run_dir: Path, gap_id: str, salt: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str | None]:
    """Copy the base tenant into `run_dir` and run the planner once against that copy alone.
    Returns (result, adk_records, error): `result` is run_planner_async's full return value
    (including "events") when the run completed, else None; `adk_records` is on_event's raw feed,
    unshrunk -- one {"kind": "user", ...} record for the exact initial message the model saw, then
    one {"kind": "event", ...} per ADK event; `error` is a short message when it raised. A run is
    never dropped either way -- the caller always has something to write."""
    shutil.copytree(base_dir, run_dir)
    records: list[dict[str, Any]] = []

    def on_event(kind: str, obj: Any) -> None:
        if kind == "user":
            records.append({"kind": "user", "content": _dump(obj)})
        else:
            records.append({"kind": "event", "event": _dump(obj)})

    try:
        result = await run_planner_async(str(run_dir), gap_id, salt=salt, on_event=on_event)
        return result, records, None
    except Exception as e:
        return None, records, f"{type(e).__name__}: {e}"


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


async def _record_one_run(base_dir: Path, work_root: Path, gap_id: str, i: int) -> dict[str, str]:
    """<out>/run_0i/*'s exact file contents, staged in memory (nothing is written here)."""
    tag = f"run_{i:02d}"
    run_dir = work_root / tag
    t0 = time.perf_counter()
    started_at = _utcnow_iso()
    result, adk_records, error = await _run_once(base_dir, run_dir, gap_id, salt=f"rec{i}")
    wall_time_s = round(time.perf_counter() - t0, 3)
    finished_at = _utcnow_iso()

    trace_text = ""
    run_id = (result or {}).get("run_id")
    if run_id:
        trace_path = run_dir / "events" / f"{run_id}.jsonl"
        if trace_path.exists():
            trace_text = trace_path.read_text(encoding="utf-8")  # exactly the store's own file

    adk_text = "".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in adk_records)

    play = (result or {}).get("play")
    result_out = {k: v for k, v in (result or {}).items() if k != "events"}
    result_out.update({"wall_time_s": wall_time_s, "started_at": started_at, "finished_at": finished_at})
    if error:
        result_out["error"] = error

    files = {
        f"{tag}/trace.jsonl": trace_text,
        f"{tag}/adk_events.jsonl": adk_text,
        f"{tag}/result.json": json.dumps(result_out, indent=2, ensure_ascii=False) + "\n",
    }
    if play:
        files[f"{tag}/play.json"] = json.dumps(play, indent=2, ensure_ascii=False) + "\n"
    return files


# ------------------------------------------------------------------------------------- summary
#
# Every field below is parsed back out of the exact strings staged for <out>/*, not out of a
# variable retained from the run loop -- so a bug that let the written file and an in-memory value
# disagree cannot hide behind a self-consistent summary.

def _rejection(resp: dict[str, Any]) -> dict[str, Any]:
    errors = resp.get("errors") or []
    rule_ids = [m.group(1) for e in errors for m in [re.match(r"^guardrail (\S+):", e)] if m]
    return {"guardrail_rule_ids": rule_ids, "errors_preview": "; ".join(errors)[:200]}


def _play_shape(play: dict[str, Any] | None) -> dict[str, Any] | None:
    if not play:
        return None
    audience = play.get("audience") or {}
    eo = play.get("expected_outcome") or {}
    return {
        "mechanic": play.get("mechanic"), "mechanic_params": play.get("mechanic_params"),
        "audience": {"segment_ids": audience.get("segment_ids"), "size_after_consent": audience.get("size_after_consent")},
        "expected_outcome": {"units": eo.get("units"), "margin_inr": eo.get("margin_inr")},
    }


def _summarise_run(i: int, files: dict[str, str]) -> dict[str, Any]:
    tag = f"run_{i:02d}"
    result = json.loads(files[f"{tag}/result.json"])
    trace = [json.loads(line) for line in files.get(f"{tag}/trace.jsonl", "").splitlines() if line.strip()]
    play = json.loads(files[f"{tag}/play.json"]) if f"{tag}/play.json" in files else None
    run_summary = next((e for e in reversed(trace) if e.get("kind") == "run_summary"), None)

    propose_responses = [(e.get("function_response") or {}).get("response") or {} for e in trace if (e.get("function_response") or {}).get("name") == "propose_play"]
    rejections = [_rejection(r) for r in propose_responses if not r.get("valid")]
    passed_first_try = bool(propose_responses) and bool(propose_responses[0].get("valid"))
    passed_after_revision = (not passed_first_try) and any(bool(r.get("valid")) for r in propose_responses[1:])
    # the run_summary's own "usage" is the run's TOTAL, not one model call -- excluded here so
    # model_calls counts distinct calls that returned usage metadata, not that total plus itself.
    model_calls = sum(1 for e in trace if e.get("usage") and e.get("kind") != "run_summary")

    return {
        "run_id": result.get("run_id"), "wall_time_s": result.get("wall_time_s"), "elapsed_ms": result.get("elapsed_ms"),
        "iterations": result.get("iterations"), "status": result.get("status"), "source": result.get("source"),
        "planner_source": result.get("planner_source"), "fallback_reason": result.get("fallback_reason"),
        "propose_play_attempts": len(propose_responses), "rejections": rejections,
        "passed_first_try": passed_first_try, "passed_after_revision": passed_after_revision,
        "fell_back": result.get("planner_source") == "deterministic_fallback",
        "winning_play_shape": _play_shape(play),
        "token_totals": (run_summary or {}).get("usage") or {}, "model_calls": model_calls,
    }


def _prompt_version() -> str:
    changelog = (PROMPTS_DIR / "CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(r"^- (v\d+) \(", changelog, re.M)
    if not m:
        raise RecorderAbort("could not find a '- vN (...)' version heading in agents/planner/prompts/CHANGELOG.md")
    return m.group(1)


def _wall_time_stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "median": None, "max": None}
    return {"min": round(min(values), 3), "median": round(median(values), 3), "max": round(max(values), 3)}


def build_summary(gap_id: str, backend: str, models: dict[str, Any], deadline_s: float, taal_now: str, run_files: list[dict[str, str]]) -> dict[str, Any]:
    runs = [_summarise_run(i, files) for i, files in enumerate(run_files, start=1)]
    wall_times = [r["wall_time_s"] for r in runs if isinstance(r.get("wall_time_s"), int | float)]
    model_id = models["ids"]["flash"] if backend == "vertex" else "stub-planner"
    return {
        "recorded_at": _utcnow_iso(),
        "git_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip(),
        "backend": backend, "model": model_id,
        "prompt_version": _prompt_version(),
        "prompt_sha256": hashlib.sha256((PROMPTS_DIR / "planner.md").read_bytes()).hexdigest(),
        "thinking": models.get("thinking", {}),
        "deadline_s": deadline_s, "taal_now": taal_now, "gap_id": gap_id,
        "runs": runs,
        "aggregate": {
            "n_runs": len(runs),
            "status_counts": dict(Counter(r["status"] for r in runs)),
            "source_counts": dict(Counter(r["source"] for r in runs)),
            "passed_first_try_count": sum(1 for r in runs if r["passed_first_try"]),
            "passed_after_revision_count": sum(1 for r in runs if r["passed_after_revision"]),
            "fell_back_count": sum(1 for r in runs if r["fell_back"]),
            "wall_time_s": _wall_time_stats(wall_times),
        },
    }


# --------------------------------------------------------------------------------------- main

async def _main_async(args: argparse.Namespace) -> dict[str, Any]:
    backend = _resolve_backend(args.allow_stub)
    models = load_models()
    tenant_config = os.environ["TAAL_TENANT_CONFIG"]
    taal_now = os.environ["TAAL_NOW"]
    deadline_s = float(os.environ.get("TAAL_PLANNER_DEADLINE_S", DEFAULT_DEADLINE_S))

    with tempfile.TemporaryDirectory(prefix="taal-recorder-") as work_root_s:
        work_root = Path(work_root_s)
        base_dir = prepare_base_tenant(args.base_data, work_root, tenant_config, taal_now)
        gap_context = _gap_context(base_dir, args.gap)

        outputs: dict[str, str] = {"flagship_gap.json": json.dumps(gap_context, indent=2, ensure_ascii=False) + "\n"}
        run_files: list[dict[str, str]] = []
        for i in range(1, args.runs + 1):
            files = await _record_one_run(base_dir, work_root, args.gap, i)
            run_files.append(files)
            outputs.update(files)

        summary = build_summary(args.gap, backend, models, deadline_s, taal_now, run_files)
        outputs["summary.json"] = json.dumps(summary, indent=2, ensure_ascii=False) + "\n"

        _scan_or_abort(outputs)

        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        for rel, content in outputs.items():
            p = out_dir / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")

    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gap", required=True, help="gap_id to plan, e.g. gap_chips_ds07")
    ap.add_argument("--runs", type=int, default=5, help="independent planner runs to record (default 5)")
    ap.add_argument("--out", required=True, help="output directory, e.g. eval/raw/planner_real_traces_2026-09-27")
    ap.add_argument("--base-data", default=None, help="reuse (or build once into) a tenant dir instead of a throwaway one; must come from data.generator + jobs.sense, never harness.seed_plays")
    ap.add_argument("--allow-stub", action="store_true", help="allow TAAL_MODEL_BACKEND=stub, to test this tool's own mechanics; its output is never eligible for seeding")
    args = ap.parse_args(argv)
    os.environ.setdefault("TAAL_TENANT_CONFIG", DEFAULT_TENANT_CONFIG)
    os.environ.setdefault("TAAL_NOW", DEFAULT_TAAL_NOW)
    try:
        summary = asyncio.run(_main_async(args))
    except RecorderAbort as e:
        print(f"record_flagship_traces: {e}", file=sys.stderr)
        return 1
    print(f"record_flagship_traces: wrote {args.runs} run(s) for {args.gap} to {args.out}")
    print(json.dumps(summary["aggregate"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
