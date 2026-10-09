"""Record one real planner run per selected gap and keep the full event log.

    TAAL_MODEL_BACKEND=vertex GOOGLE_CLOUD_PROJECT=... TAAL_PLANNER_DEADLINE_S=120 \
        uv run python -m harness.record_planner_traces [--concurrency 4] [--gaps gap_a,gap_b]

Reads the gap list from the newest eval/raw/planner_evalset_selection_*.json (harness/select_eval_gaps.py).
Writes eval/raw/planner_traces_<date>/:

  <gap_id>.jsonl   one line per record, in order: {"kind": "user"} (the exact initial message the
                   model saw), {"kind": "event"} per ADK event (unshrunk: every tool call with full
                   args, every tool response incl. guardrail results, model text, usage_metadata),
                   and a closing {"kind": "result"} (status, planner_source, fallback reason,
                   iterations, elapsed, the final play).
  summary.json     per gap: tool names in order, propose_play verdicts (revisions), guardrail
                   failures, final play id, token counts; totals and a cost figure computed from
                   the recorded token counts at config/models.toml [pricing] (list-rate estimates,
                   labelled projected -- not a billing figure).

Every run gets its own copy-on-write sandbox over the tenant, so concurrent runs never share state
and the base tenant is never written. Concurrency is capped at 4.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agents.gate.config import load_models
from agents.gate.store import OverlayStore
from harness.checklists import ROOT

MAX_CONCURRENCY = 4
PROMPT = ROOT / "agents" / "planner" / "prompts" / "planner.md"
CHANGELOG = ROOT / "agents" / "planner" / "prompts" / "CHANGELOG.md"
# the tables run_planner reads (tests/agents/test_planner.py::_run materialises the same list)
TABLES = ("gaps", "plays", "products", "nodes", "customers", "affinity", "consent", "segments", "estimator_priors", "play_assignments", "inventory_batches", "inbound", "order_lines", "play_outcomes", "sense_runs", "policy")


def latest_selection() -> Path:
    found = sorted((ROOT / "eval" / "raw").glob("planner_evalset_selection_*.json"))
    if not found:
        raise SystemExit("record_planner_traces: no eval/raw/planner_evalset_selection_*.json; run `python -m harness.select_eval_gaps` first")
    return found[-1]


def prompt_version() -> str:
    for line in CHANGELOG.read_text(encoding="utf-8").splitlines():
        if line.startswith("- v"):
            return line[2:].split(" ", 1)[0]
    return "unknown"


def sandbox(base: Path, root: Path) -> OverlayStore:
    s = OverlayStore(base, root)
    s.reset()
    for t in TABLES:
        s._materialise(t)
    (s.root / "manifest.json").write_bytes((base / "manifest.json").read_bytes())
    return s


def _dump(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json", exclude_none=True)
    return obj


def trace_facts(records: list[dict[str, Any]]) -> dict[str, Any]:
    """What summary.json and the evalset builder need from one recorded trace."""
    tools: list[str] = []
    verdicts: list[dict[str, Any]] = []
    guardrail_failures: list[str] = []
    texts: list[str] = []
    tokens = {"prompt": 0, "candidates": 0, "thoughts": 0, "cached": 0, "model_calls": 0}
    for r in records:
        if r.get("kind") != "event":
            continue
        ev = r["event"]
        usage = ev.get("usage_metadata") or {}
        if usage:
            tokens["model_calls"] += 1
            tokens["prompt"] += int(usage.get("prompt_token_count") or 0)
            tokens["candidates"] += int(usage.get("candidates_token_count") or 0)
            tokens["thoughts"] += int(usage.get("thoughts_token_count") or 0)
            tokens["cached"] += int(usage.get("cached_content_token_count") or 0)
        parts = (ev.get("content") or {}).get("parts") or []
        # ADK's final response is an event with no tool call or response in it; narration the model
        # writes alongside a tool call is not one
        final_event = not any(p.get("function_call") or p.get("function_response") for p in parts)
        for part in parts:
            if part.get("function_call"):
                tools.append(part["function_call"]["name"])
            if part.get("function_response"):
                fr = part["function_response"]
                resp = fr.get("response") or {}
                if fr["name"] == "propose_play":
                    verdicts.append({"valid": bool(resp.get("valid")), "errors": resp.get("errors") or []})
                    guardrail_failures += [e for e in resp.get("errors") or [] if e.startswith("guardrail ")]
                if fr["name"] == "check_guardrails":
                    guardrail_failures += [f"guardrail {x['rule']}: {x.get('detail', '')}" for x in resp.get("results") or [] if not x.get("passed")]
            if part.get("text") and final_event and ev.get("author") == "planner" and not part.get("thought"):
                texts.append(part["text"])
    result = next((r for r in records if r.get("kind") == "result"), {})
    return {
        "tool_names": tools,
        "propose_play_verdicts": [v["valid"] for v in verdicts],
        "revisions": sum(1 for v in verdicts if not v["valid"]),
        "guardrail_failures": guardrail_failures,
        "final_text": texts[-1] if texts else "",
        "final_play_id": (result.get("play") or {}).get("play_id") if result.get("planner_source") == "model" else None,
        "status": result.get("status"),
        "planner_source": result.get("planner_source"),
        "fallback_reason": result.get("fallback_reason"),
        "iterations": result.get("iterations"),
        "elapsed_ms": result.get("elapsed_ms"),
        "tokens": tokens,
    }


def cost_usd(tokens: dict[str, int], pricing: dict[str, Any]) -> float:
    """Tokens at the config list-rate estimates: uncached prompt at the input rate, cached prompt at
    the discounted rate, candidates + thinking at the output rate."""
    uin = float(pricing.get("usd_per_million_input", 0.75)) / 1e6
    uout = float(pricing.get("usd_per_million_output", 3.75)) / 1e6
    disc = float(pricing.get("cached_input_discount", 0.9))
    cached = tokens["cached"]
    return (tokens["prompt"] - cached) * uin + cached * uin * (1 - disc) + (tokens["candidates"] + tokens["thoughts"]) * uout


async def record_one(base: Path, gap_id: str, out_dir: Path, work: Path, backend: str, deadline_s: float, sem: asyncio.Semaphore) -> dict[str, Any]:
    from agents.planner.run import run_planner_async

    async with sem:
        store = sandbox(base, work / gap_id)
        records: list[dict[str, Any]] = []

        def on_event(kind: str, obj: Any) -> None:
            if kind == "user":
                records.append({"kind": "user", "content": _dump(obj)})
            else:
                records.append({"kind": "event", "event": _dump(obj)})

        t0 = time.time()
        try:
            out = await run_planner_async(store.root, gap_id, backend=backend, deadline_s=deadline_s, on_event=on_event)
            records.append({"kind": "result", **{k: v for k, v in out.items() if k != "events"}})
        except Exception as e:  # a crashed run is still a recorded outcome, not a silent skip
            records.append({"kind": "result", "status": "error", "error": f"{type(e).__name__}: {e}", "elapsed_ms": int((time.time() - t0) * 1000)})
        finally:
            shutil.rmtree(work / gap_id, ignore_errors=True)
        (out_dir / f"{gap_id}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in records), encoding="utf-8")
        facts = trace_facts(records)
        print(f"  {gap_id:24s} {facts['status'] or 'error':9s} source={facts['planner_source']} tools={'>'.join(facts['tool_names'])} {facts['elapsed_ms']}ms", flush=True)
        return {"gap_id": gap_id, **facts}


async def main_async(args: argparse.Namespace) -> int:
    models = load_models()
    backend = args.backend or models["backend"]
    if backend == "vertex" and not os.environ.get(models["vertex"]["project_env"]):
        print("record_planner_traces: vertex backend needs GOOGLE_CLOUD_PROJECT (and credentials); nothing run")
        return 1
    selection_path = Path(args.selection) if args.selection else latest_selection()
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    gaps = [g["gap_id"] for g in selection["gaps"]]
    if args.gaps:
        wanted = args.gaps.split(",")
        gaps = [g for g in gaps if g in wanted]
    started = datetime.now(UTC)
    out_dir = Path(args.out) if args.out else ROOT / "eval" / "raw" / f"planner_traces_{started.date().isoformat()}"
    out_dir.mkdir(parents=True, exist_ok=True)
    base = Path(args.data).resolve()
    concurrency = min(MAX_CONCURRENCY, max(1, args.concurrency))
    print(f"record_planner_traces: backend={backend} model={models['ids']['flash'] if backend == 'vertex' else 'stub-planner'} prompt={prompt_version()} deadline={args.deadline}s concurrency={concurrency} gaps={len(gaps)} -> {out_dir}")
    sem = asyncio.Semaphore(concurrency)
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="taal_traces_") as work:
        rows = await asyncio.gather(*(record_one(base, g, out_dir, Path(work), backend, args.deadline, sem) for g in gaps))
    pricing = models.get("pricing", {})
    totals = {k: sum(r["tokens"][k] for r in rows) for k in ("prompt", "candidates", "thoughts", "cached", "model_calls")}
    for r in rows:
        r["cost_usd_projected"] = round(cost_usd(r["tokens"], pricing), 6)
    usd = cost_usd(totals, pricing)
    summary = {
        "recorded_at": started.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "label": "measured" if backend == "vertex" else "synthetic (stub backend: a scripted stand-in, not the model)",
        "backend": backend,
        "model": models["ids"]["flash"] if backend == "vertex" else "stub-planner",
        "region": os.environ.get("GOOGLE_CLOUD_LOCATION") or models["vertex"].get("location"),
        "prompt_version": prompt_version(),
        "prompt_sha256": hashlib.sha256(PROMPT.read_bytes()).hexdigest(),
        "deadline_s": args.deadline,
        "concurrency": concurrency,
        "selection": str(selection_path.relative_to(ROOT)) if selection_path.is_relative_to(ROOT) else str(selection_path),
        "wall_s": round(time.time() - t0, 1),
        "counts": {
            "gaps": len(rows),
            "planner_source_model": sum(1 for r in rows if r["planner_source"] == "model"),
            "deterministic_fallback": sum(1 for r in rows if r["planner_source"] == "deterministic_fallback"),
            "errors": sum(1 for r in rows if r["status"] == "error"),
        },
        "tokens": totals,
        "cost": {
            "usd_projected": round(usd, 4),
            "inr_projected": round(usd * float(pricing.get("inr_per_usd", 83.0)), 2),
            "method": "recorded usage_metadata token counts x config/models.toml [pricing] list-rate estimates (thinking tokens at the output rate); projected, not a billing-export figure",
        },
        "gaps": rows,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    c = summary["counts"]
    print(f"record_planner_traces: {c['planner_source_model']}/{c['gaps']} model plays, {c['deterministic_fallback']} fallbacks, {c['errors']} errors; tokens {totals}; ~${summary['cost']['usd_projected']} projected")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selection", default=None)
    ap.add_argument("--gaps", default=None, help="comma-separated subset of the selection")
    ap.add_argument("--out", default=None)
    ap.add_argument("--data", default=os.environ.get("TAAL_DATA_DIR", ".local/data"))
    ap.add_argument("--backend", default=None, help="defaults to TAAL_MODEL_BACKEND")
    ap.add_argument("--concurrency", type=int, default=MAX_CONCURRENCY)
    ap.add_argument("--deadline", type=float, default=float(os.environ.get("TAAL_PLANNER_DEADLINE_S", 120)))
    return asyncio.run(main_async(ap.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
