"""Run the Planner on one gap and persist the trace (events/<run_id>.jsonl).

    python -m agents.planner --gap gap_chips_ds07 [--policy-file policy.txt --policy-version v2]
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from google.adk.runners import InMemoryRunner, Runner
from google.genai import types

from agents.gate.config import load_models, load_tenant
from agents.vertex_sessions import build_session_service

from . import drafting, governor
from . import tools as pt
from .agent import build_planner
from .context import PlannerContext, reset_context, set_context
from .deterministic import deterministic_plan

APP = "taal_planner"

# A live Gemini planner call that exceeds this many seconds falls back to the deterministic draft
# (deterministic.py) rather than let a demo-facing request run unbounded. The deployed service
# overrides this default through TAAL_PLANNER_DEADLINE_S (infra/deploy.sh, being changed in the
# same branch as this file); the async re-plan endpoint no longer holds a request open for the
# planner, so that override no longer has to fit under a synchronous HTTP response budget.
DEFAULT_DEADLINE_S = 8.0

# Every play's provenance is one of these four. `resolve_source` below decides which, for a run
# just executed; "recorded_gemini" is not one of its outputs -- it is reserved for a play whose
# play_json was captured from a real historical Vertex call and is now served as fixed data
# (never re-run), distinct from "scripted_stub" (the deterministic script standing in for Gemini
# in CI, DECISIONS on the stub backend) producing new plays every run.
PLAN_SOURCES = ("recorded_gemini", "scripted_stub", "deterministic_rules", "live_gemini")


def resolve_source(backend: str, planner_source: str | None, skipped: bool) -> str:
    """Which of PLAN_SOURCES a run's play (or attempted play) came from.

    `backend` must already be resolved the way `build_planner` resolves it (`backend or
    load_models()["backend"]`) -- this function does not read TAAL_MODEL_BACKEND itself.

    - the Cost Governor skipped the gap (no planner run happened at all), or the deterministic
      fallback is what produced the play (`planner_source == "deterministic_fallback"`, set only
      when that fallback succeeds): "deterministic_rules".
    - otherwise (`planner_source == "model"`): the backend's own model source, "live_gemini" for
      vertex or "scripted_stub" for stub. This is the same value whether the model itself produced
      the play or status ended up `no_play` (the model path was attempted and the deterministic
      fallback that always follows it was also unable to produce one) -- `planner_source` stays
      "model" in both cases, and the model path is what this run actually attempted either way, so
      it is what the source names.
    """
    if skipped or planner_source == "deterministic_fallback":
        return "deterministic_rules"
    return "live_gemini" if backend == "vertex" else "scripted_stub"


def make_run_id(gap_id: str, policy_version: str, salt: str = "") -> str:
    h = hashlib.sha256(f"{gap_id}|{policy_version}|{salt}".encode()).hexdigest()[:8]
    return f"run_{gap_id[4:]}_{policy_version}_{h}"


_USAGE_FIELDS = ("prompt_token_count", "candidates_token_count", "thoughts_token_count", "cached_content_token_count", "total_token_count")


def _event_record(ev: Any, seq: int, t0: float, run_id: str) -> dict[str, Any]:
    rec: dict[str, Any] = {"seq": seq, "run_id": run_id, "invocation_id": ev.invocation_id, "author": ev.author, "timestamp": ev.timestamp, "ts_offset_ms": int((ev.timestamp - t0) * 1000), "level": "info"}
    if ev.usage_metadata is not None:
        usage = {f: getattr(ev.usage_metadata, f) for f in _USAGE_FIELDS if getattr(ev.usage_metadata, f, None) is not None}
        if usage:
            rec["usage"] = usage
    if ev.model_version:
        rec["model_version"] = ev.model_version
    for part in (ev.content.parts if ev.content and ev.content.parts else []):
        if part.text:
            rec["text"] = part.text
            if part.text.lower().startswith("guardrail failed"):
                rec["level"] = "warn"
            if part.text.startswith("DONE"):
                rec["level"] = "ok"
        if part.function_call:
            args = dict(part.function_call.args or {})
            rec["function_call"] = {"name": part.function_call.name, "args": _shrink(args)}
            rationale = (args.get("play") or {}).get("rationale") if part.function_call.name == "propose_play" and isinstance(args.get("play"), dict) else None
            if rationale:
                rec["rationale"] = str(rationale)  # the args above cap strings at 400 chars; the rejected wording is shown in full
        if part.function_response:
            resp = dict(part.function_response.response or {})
            rec["function_response"] = {"name": part.function_response.name, "response": _shrink(resp)}
            if part.function_response.name == "propose_play" and not resp.get("valid"):
                rec["rejections"] = parse_rejections(resp.get("errors"))
            if part.function_response.name == "check_guardrails" and not resp.get("all_passed", True):
                rec["level"] = "warn"
            if part.function_response.name == "propose_play":
                rec["level"] = "ok" if resp.get("valid") else "error"
    if ev.actions and ev.actions.escalate:
        rec["escalate"] = True
    return rec


_GUARDRAIL_ERROR = re.compile(r"^guardrail (\w+): (.*)$", re.S)


def parse_rejections(errors: list[Any] | None) -> list[dict[str, str]]:
    """propose_play's error strings -> [{guardrail, reason}], one per failure, for the trace panel.
    "guardrail <rule>: <detail>" names its rule; the other kinds of rejection get a fixed name."""
    out = []
    for e in errors or []:
        text = str(e)
        if m := _GUARDRAIL_ERROR.match(text):
            out.append({"guardrail": m.group(1), "reason": m.group(2)})
        elif text.startswith("runtime invariant: "):
            out.append({"guardrail": "runtime_invariant", "reason": text.removeprefix("runtime invariant: ")})
        elif text.startswith("target lot is past"):
            out.append({"guardrail": "online_sellby", "reason": text})
        else:
            out.append({"guardrail": "schema", "reason": text})
    return out


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
    audiences = pt.get_candidate_audiences(gap["sku"], [gap["node_id"]], drafting.OBJECTIVE_BY_GAP[gap["type"]], gap_id=gap_id)
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


async def run_planner_async(data_dir: str | Path, gap_id: str, policy_text: str | None = None, policy_version: str | None = None, backend: str | None = None, salt: str = "", deadline_s: float | None = None, on_event: Callable[[str, Any], None] | None = None) -> dict[str, Any]:
    """`on_event`, when given, is called with ("user", <initial Content>) once and then ("event",
    <ADK Event>) for every event, unshrunk -- the trace recorder (harness/record_planner_traces.py)
    uses it to keep full tool args, responses and token usage. None changes nothing."""
    tenant = load_tenant()
    models = load_models()
    resolved_backend = backend or models["backend"]
    model_label = models["ids"]["flash"] if resolved_backend == "vertex" else "stub-planner"
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
        source = resolve_source(resolved_backend, None, skipped=True)
        finished = time.time()
        ctx.store.append_event(run_id, {
            "seq": 1, "run_id": run_id, "invocation_id": "", "author": "planner_run", "kind": "run_summary",
            "timestamp": finished, "ts_offset_ms": int((finished - started) * 1000), "level": "warn",
            "source": source, "status": "skipped", "play_id": None, "iterations": 0, "elapsed_ms": int((finished - started) * 1000),
            "fallback_reason": None, "backend": resolved_backend, "model": model_label,
            "text": f"Run finished: governor skipped ({why})",
        })
        return {"run_id": run_id, "play": None, "status": "skipped", "reason": why, "iterations": 0, "events": ctx.store.read_events(run_id), "source": source}
    token = set_context(ctx)
    try:
        agent = build_planner(tenant, ctx.policy_text, ctx.policy_version, run_id, ctx.as_of.isoformat(), backend)
        session_service = build_session_service(scope="planner")
        if session_service is None:
            runner = InMemoryRunner(agent=agent, app_name=APP)
        else:
            from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
            from google.adk.memory.in_memory_memory_service import InMemoryMemoryService

            runner = Runner(app_name=APP, agent=agent, artifact_service=InMemoryArtifactService(), session_service=session_service, memory_service=InMemoryMemoryService())
        session = await runner.session_service.create_session(app_name=APP, user_id="planner", session_id=run_id)
        msg = _initial_message(ctx, gap_id)
        if on_event is not None:
            on_event("user", msg)
        seq, iterations, t0, attempts = 1, 0, None, 0
        proposed = None
        usage_totals: dict[str, int] = {}
        deadline = DEFAULT_DEADLINE_S if deadline_s is None else deadline_s
        deadline = float(os.environ.get("TAAL_PLANNER_DEADLINE_S", deadline))
        timed_out = False

        async def _drain() -> None:
            nonlocal seq, iterations, t0, proposed, attempts
            async for ev in runner.run_async(user_id="planner", session_id=session.id, new_message=msg):
                if t0 is None:
                    t0 = ev.timestamp
                if on_event is not None:
                    on_event("event", ev)
                rec = _event_record(ev, seq, t0, run_id)
                if (rec.get("function_call") or rec.get("function_response") or {}).get("name") == "propose_play":
                    if "function_call" in rec:
                        attempts += 1  # a propose_play call opens the next attempt; its response carries the same number
                    rec["attempt"] = attempts
                ctx.store.append_event(run_id, rec)
                seq += 1
                for field, count in (rec.get("usage") or {}).items():
                    usage_totals[field] = usage_totals.get(field, 0) + count
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
            fallback_reason = f"deadline exceeded after {deadline:g}s" if timed_out else f"no_play after {iterations} iteration(s)"
            ctx.store.append_event(run_id, {"seq": seq, "run_id": run_id, "invocation_id": "", "author": "planner_fallback", "timestamp": time.time(), "ts_offset_ms": int((time.time() - started) * 1000), "text": f"{fallback_reason}; falling back to the deterministic draft", "level": "warn"})
            seq += 1
            play = deterministic_plan(ctx, gap_id)
            if play is not None:
                planner_source = "deterministic_fallback"

        source = resolve_source(resolved_backend, planner_source, skipped=False)
        if play is not None:
            play["source"] = source
            ctx.store.upsert("plays", "play_id", pt.play_row(ctx, play))
        status = "proposed" if play else "no_play"
        finished = time.time()
        elapsed_ms = int((finished - started) * 1000)
        if play is not None and fallback_reason is None:
            text = f"Run finished: play proposed ({source}) in {elapsed_ms / 1000:.1f} s"
        elif play is not None:
            text = f"Run finished: {source} fallback ({fallback_reason})"
        else:
            text = f"Run finished: no play produced ({source}); {fallback_reason}"
        summary: dict[str, Any] = {
            "seq": seq, "run_id": run_id, "invocation_id": "", "author": "planner_run", "kind": "run_summary",
            "timestamp": finished, "ts_offset_ms": elapsed_ms, "level": "ok" if play else "warn",
            "source": source, "status": status, "play_id": play["play_id"] if play else None, "iterations": iterations,
            "elapsed_ms": elapsed_ms, "fallback_reason": fallback_reason, "backend": resolved_backend, "model": model_label,
            "text": text,
        }
        if usage_totals:
            summary["usage"] = usage_totals
        ctx.store.append_event(run_id, summary)
        return {
            "run_id": run_id, "play": play, "status": status, "iterations": iterations,
            "events": ctx.store.read_events(run_id), "policy_version": ctx.policy_version,
            "elapsed_ms": elapsed_ms, "planner_source": planner_source, "fallback_reason": fallback_reason,
            "source": source,
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
