"""Run the Planner on one gap and persist the trace (events/<run_id>.jsonl).

    python -m agents.planner --gap gap_chips_ds07 [--policy-file policy.txt --policy-version v2]
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from google.adk.runners import InMemoryRunner
from google.genai import types

from agents.gate.config import load_tenant

from . import drafting, governor
from . import tools as pt
from .agent import build_planner
from .context import PlannerContext, reset_context, set_context
from .deterministic import deterministic_plan

APP = "taal_planner"

# A live Gemini planner call that exceeds this many seconds falls back to the deterministic draft
# (deterministic.py) rather than let a demo-facing request run unbounded. Comfortably under the
# entry's 10s response budget, leaving headroom for API/network overhead on top of this function.
DEFAULT_DEADLINE_S = 8.0


def make_run_id(gap_id: str, policy_version: str, salt: str = "") -> str:
    h = hashlib.sha256(f"{gap_id}|{policy_version}|{salt}".encode()).hexdigest()[:8]
    return f"run_{gap_id[4:]}_{policy_version}_{h}"


def _event_record(ev: Any, seq: int, t0: float, run_id: str) -> dict[str, Any]:
    rec: dict[str, Any] = {"seq": seq, "run_id": run_id, "invocation_id": ev.invocation_id, "author": ev.author, "timestamp": ev.timestamp, "ts_offset_ms": int((ev.timestamp - t0) * 1000), "level": "info"}
    for part in (ev.content.parts if ev.content and ev.content.parts else []):
        if part.text:
            rec["text"] = part.text
            if part.text.lower().startswith("guardrail failed"):
                rec["level"] = "warn"
            if part.text.startswith("DONE"):
                rec["level"] = "ok"
        if part.function_call:
            rec["function_call"] = {"name": part.function_call.name, "args": _shrink(dict(part.function_call.args or {}))}
        if part.function_response:
            resp = dict(part.function_response.response or {})
            rec["function_response"] = {"name": part.function_response.name, "response": _shrink(resp)}
            if part.function_response.name == "check_guardrails" and not resp.get("all_passed", True):
                rec["level"] = "warn"
            if part.function_response.name == "propose_play":
                rec["level"] = "ok" if resp.get("valid") else "error"
    if ev.actions and ev.actions.escalate:
        rec["escalate"] = True
    return rec


def _shrink(obj: Any, depth: int = 0) -> Any:
    """Keep traces readable: drop long lists beyond 5 items, cap strings."""
    if isinstance(obj, dict):
        return {k: _shrink(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_shrink(v, depth + 1) for v in obj[:8]] + ([f"... {len(obj) - 8} more"] if len(obj) > 8 else [])
    if isinstance(obj, str) and len(obj) > 400:
        return obj[:400] + "..."
    return obj


def _context_block(ctx: PlannerContext, gap_id: str) -> dict[str, Any]:
    """The plain-read tool results (get_gap, get_candidate_audiences, get_past_plays) gathered up
    front instead of one model round trip each. These are deterministic store reads, not a
    decision the model needs to make; the tools stay registered below for the model to re-check
    one if it wants to, but the common path never has to ask for them."""
    gap = pt.get_gap(gap_id)
    audiences = pt.get_candidate_audiences(gap["sku"], [gap["node_id"]], drafting.OBJECTIVE_BY_GAP[gap["type"]])
    candidates = drafting.candidate_mechanics(gap, ctx.policy_text)
    category = (gap.get("product") or {}).get("category", "")
    past_plays: list[dict[str, Any]] = []
    seen: set[str] = set()
    for c in candidates:
        for row in pt.get_past_plays(gap["sku"], category, c["mechanic"]):
            if row["play_id"] not in seen:
                seen.add(row["play_id"])
                past_plays.append(row)
    return {"gap": gap, "candidate_audiences": audiences, "past_plays": past_plays[:10]}


def _initial_message(ctx: PlannerContext, gap_id: str) -> types.Content:
    context = _context_block(ctx, gap_id)
    context_json = json.dumps(context, ensure_ascii=False)
    text = (
        f"Plan gap_id={gap_id} policy_version={ctx.policy_version}\n"
        "Reply DONE <play_id> when propose_play accepts.\n\n"
        "## Context (already fetched -- do not call get_gap, get_candidate_audiences or "
        "get_past_plays again unless you specifically need to re-check one of them)\n"
        f"```json\n{context_json}\n```"
    )
    return types.Content(role="user", parts=[types.Part(text=text)])


async def run_planner_async(data_dir: str | Path, gap_id: str, policy_text: str | None = None, policy_version: str | None = None, backend: str | None = None, salt: str = "", deadline_s: float | None = None) -> dict[str, Any]:
    tenant = load_tenant()
    probe = PlannerContext.build(data_dir, run_id="probe", policy_text=policy_text, policy_version=policy_version, tenant=tenant)
    run_id = make_run_id(gap_id, probe.policy_version, salt)
    ctx = PlannerContext.build(data_dir, run_id=run_id, policy_text=policy_text, policy_version=policy_version, tenant=tenant)
    gap_rows = ctx.store.find("gaps", gap_id=gap_id)
    if not gap_rows:
        raise KeyError(f"unknown gap {gap_id}")
    eligible, why = governor.planner_eligible(gap_rows[-1], tenant)
    started = time.time()
    # a run id names one run: a repeat (same gap, same policy) replaces its trace instead of appending
    trace = ctx.store.root / "events" / f"{run_id}.jsonl"
    if trace.exists():
        trace.unlink()
    ctx.store.append_event(run_id, {"seq": 0, "run_id": run_id, "invocation_id": "", "author": "cost_governor", "timestamp": started, "ts_offset_ms": 0, "text": why, "level": "info" if eligible else "warn"})
    if not eligible:
        return {"run_id": run_id, "play": None, "status": "skipped", "reason": why, "iterations": 0, "events": ctx.store.read_events(run_id)}
    token = set_context(ctx)
    try:
        agent = build_planner(tenant, ctx.policy_text, ctx.policy_version, run_id, ctx.as_of.isoformat(), backend)
        runner = InMemoryRunner(agent=agent, app_name=APP)
        session = await runner.session_service.create_session(app_name=APP, user_id="planner", session_id=run_id)
        msg = _initial_message(ctx, gap_id)
        seq, iterations, t0 = 1, 0, None
        proposed = None
        deadline = DEFAULT_DEADLINE_S if deadline_s is None else deadline_s
        deadline = float(os.environ.get("TAAL_PLANNER_DEADLINE_S", deadline))
        timed_out = False

        async def _drain() -> None:
            nonlocal seq, iterations, t0, proposed
            async for ev in runner.run_async(user_id="planner", session_id=session.id, new_message=msg):
                if t0 is None:
                    t0 = ev.timestamp
                rec = _event_record(ev, seq, t0, run_id)
                ctx.store.append_event(run_id, rec)
                seq += 1
                for part in (ev.content.parts if ev.content and ev.content.parts else []):
                    if part.text and ev.author == "planner":
                        iterations += 1
                    if part.function_response and part.function_response.name == "propose_play" and (part.function_response.response or {}).get("valid"):
                        proposed = part.function_response.response["play_id"]

        try:
            await asyncio.wait_for(_drain(), timeout=deadline)
        except TimeoutError:
            timed_out = True

        play = None
        if proposed:
            row = ctx.store.find("plays", play_id=proposed)[-1]
            play = json.loads(row["play_json"])
        planner_source = "model"
        fallback_reason = None
        if play is None:
            fallback_reason = f"deadline exceeded after {deadline:.0f}s" if timed_out else f"no_play after {iterations} iteration(s)"
            ctx.store.append_event(run_id, {"seq": seq, "run_id": run_id, "invocation_id": "", "author": "planner_fallback", "timestamp": time.time(), "ts_offset_ms": int((time.time() - started) * 1000), "text": f"{fallback_reason}; falling back to the deterministic draft", "level": "warn"})
            seq += 1
            play = deterministic_plan(ctx, gap_id)
            if play is not None:
                planner_source = "deterministic_fallback"
        return {
            "run_id": run_id, "play": play, "status": "proposed" if play else "no_play", "iterations": iterations,
            "events": ctx.store.read_events(run_id), "policy_version": ctx.policy_version,
            "elapsed_ms": int((time.time() - started) * 1000), "planner_source": planner_source, "fallback_reason": fallback_reason,
        }
    finally:
        reset_context(token)


def run_planner(data_dir: str | Path, gap_id: str, **kw: Any) -> dict[str, Any]:
    return asyncio.run(run_planner_async(data_dir, gap_id, **kw))


def main(argv: list[str] | None = None) -> int:
    import os
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gap", required=True)
    ap.add_argument("--data", default=None)
    ap.add_argument("--policy-file", default=None)
    ap.add_argument("--policy-version", default=None)
    args = ap.parse_args(argv)
    policy = Path(args.policy_file).read_text(encoding="utf-8") if args.policy_file else None
    out = run_planner(args.data or os.environ.get("TAAL_DATA_DIR", ".local/data"), args.gap, policy_text=policy, policy_version=args.policy_version)
    print(json.dumps({k: v for k, v in out.items() if k != "events"}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
