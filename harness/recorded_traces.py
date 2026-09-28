"""Discover, validate and seed a committed real-Gemini planner recording (harness/
record_flagship_traces.py's output) in place of a scripted-stub run, for one gap at a time.

Wired into harness/seed_plays.py for the flagship gap only: every other demo gap keeps the stub.
No model call and no network here -- a recording is only ever read back and re-validated against
the current tenant, never re-run, so seeding stays offline and deterministic (the Docker build
included).

    discover_candidates(gap_id, raw_root) -> [Recording, ...]     # newest recording dir first
    validate_recording(data_dir, recording) -> (ok, [reason, ...])
    select_best(data_dir, gap_id, candidates) -> (best_or_None, {candidate_tag: [reason, ...]})
    seed_from_recording(data_dir, gap_id, raw_root=None) -> (result_or_None, one_line_message)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agents.gate.config import ROOT
from agents.gate.estimator import estimate
from agents.gate.guardrails import check as check_guardrails
from agents.gate.invariants import check_play_money
from agents.gate.models import Play
from agents.gate.store import LocalStore
from agents.planner import tools as pt
from agents.planner.context import PlannerContext, reset_context, set_context

RAW_ROOT_DEFAULT = ROOT / "eval" / "raw"
NUMERIC_TOLERANCE = 0.01


@dataclass
class Recording:
    """One run_0N directory inside a committed eval/raw/planner_real_traces_*/ recording."""

    dir: Path
    run_tag: str
    summary: dict[str, Any]       # the recording directory's summary.json (shared by every run in it)
    run_summary: dict[str, Any]   # summary["runs"][this run's 0-based index]
    result: dict[str, Any]        # run_0N/result.json
    play: dict[str, Any]          # run_0N/play.json
    trace_text: str = field(repr=False)  # run_0N/trace.jsonl, verbatim

    @property
    def tag(self) -> str:
        return f"{self.dir.name}/{self.run_tag}"


# ------------------------------------------------------------------------------------ discovery

def _parse_trace_records(trace_text: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in trace_text.splitlines() if line.strip()]


def _trace_run_summary(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((r for r in reversed(records) if r.get("kind") == "run_summary"), None)


def _has_reported_usage(records: list[dict[str, Any]]) -> bool:
    """True if at least one record in this trace carries a non-empty `usage` token count. A real
    Gemini call always reports ADK's usage_metadata (agents/planner/run.py's `_event_record`
    copies it onto the record whenever the event carries one); the stub backend never sets
    usage_metadata at all (agents/planner/stub_llm.py), so no stub-driven trace can produce this
    signal no matter what its summary.json/result.json/play.json/run_summary labels say -- it is
    the one check tampering with those labels alone cannot fake."""
    for rec in records:
        usage = rec.get("usage")
        if isinstance(usage, dict) and any(isinstance(v, int | float) and not isinstance(v, bool) and v > 0 for v in usage.values()):
            return True
    return False


def discover_candidates(gap_id: str, raw_root: Path | str = RAW_ROOT_DEFAULT) -> list[Recording]:
    """Every run, across every committed recording directory for `gap_id`, that could possibly be
    seeded. The estimator and guardrails run identically under both backends, so a stub run is
    structurally indistinguishable from a real one by its play/trace shape alone -- only its
    provenance labels and (for a real model call) reported token usage differ. Eligibility
    therefore requires ALL of the following to agree that this run is a genuine, completed
    real-Gemini call, not just one of them:

      - summary.json: this recording directory's own backend "vertex", and this run's own
        "source" "live_gemini" (in `summary["runs"][i]`).
      - run_0N/result.json: "source" "live_gemini" and "planner_source" "model".
      - run_0N/play.json: "source" "live_gemini".
      - run_0N/trace.jsonl's own `kind: run_summary` record (not summary.json's copy of it):
        "source" "live_gemini", "backend" "vertex", and a "model" id starting with "gemini".
      - run_0N/trace.jsonl: at least one record (any record, not only run_summary) carrying a
        non-empty `usage` token count (`_has_reported_usage` above) -- the one signal a stub run
        can never produce, whatever its labels claim.

    summary.json's own "status"/"planner_source" for the run and a play.json/trace.jsonl actually
    present on disk are also required, as before. A run recorded with the stub backend, or one
    whose labels disagree across these four files, is never included.

    Ordered newest recording directory first (`planner_real_traces_YYYY-MM-DD` sorts correctly by
    name), then by ascending run index within a directory -- the order `select_best` below breaks
    an exact margin_inr tie by (its first candidate in this order wins).
    """
    dirs = sorted((p.parent for p in Path(raw_root).glob("planner_real_traces_*/summary.json")), key=lambda p: p.name, reverse=True)
    out: list[Recording] = []
    for d in dirs:
        try:
            summary = json.loads((d / "summary.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if summary.get("gap_id") != gap_id or summary.get("backend") != "vertex":
            continue
        for i, run_summary in enumerate(summary.get("runs") or [], start=1):
            if run_summary.get("source") != "live_gemini" or run_summary.get("status") != "proposed" or run_summary.get("planner_source") != "model":
                continue
            tag = f"run_{i:02d}"
            run_dir = d / tag
            play_path, trace_path, result_path = run_dir / "play.json", run_dir / "trace.jsonl", run_dir / "result.json"
            if not (play_path.exists() and trace_path.exists() and result_path.exists()):
                continue
            try:
                play = json.loads(play_path.read_text(encoding="utf-8"))
                result = json.loads(result_path.read_text(encoding="utf-8"))
                trace_text = trace_path.read_text(encoding="utf-8")
            except (OSError, json.JSONDecodeError):
                continue
            if result.get("source") != "live_gemini" or result.get("planner_source") != "model":
                continue
            if play.get("source") != "live_gemini":
                continue
            records = _parse_trace_records(trace_text)
            trace_summary = _trace_run_summary(records)
            model = (trace_summary or {}).get("model") or ""
            if trace_summary is None or trace_summary.get("source") != "live_gemini" or trace_summary.get("backend") != "vertex" or not model.startswith("gemini"):
                continue
            if not _has_reported_usage(records):
                continue
            out.append(Recording(dir=d, run_tag=tag, summary=summary, run_summary=run_summary, result=result, play=play, trace_text=trace_text))
    return out


# ----------------------------------------------------------------------------------- validation

def _numeric_mismatches(recorded: dict[str, Any], recomputed: dict[str, Any], tol: float = NUMERIC_TOLERANCE) -> list[str]:
    """Fields where `recorded` (the play as committed) and `recomputed` (a fresh estimate() over
    the same draft) disagree -- numeric fields within `tol`, everything else (estimator_version)
    exactly."""
    problems = []
    for key in sorted(set(recorded) | set(recomputed)):
        r, c = recorded.get(key), recomputed.get(key)
        is_numeric = isinstance(r, int | float) and not isinstance(r, bool) and isinstance(c, int | float) and not isinstance(c, bool)
        ok = abs(float(r) - float(c)) <= tol if is_numeric else r == c
        if not ok:
            problems.append(f"{key}: recorded {r!r}, recomputed {c!r}")
    return problems


def validate_recording(data_dir: str | Path, rec: Recording) -> tuple[bool, list[str]]:
    """Re-derive everything about `rec.play` from the CURRENT tenant at `data_dir` and compare
    against what was recorded. `data_dir` is the seed-time store, at the point the flagship is
    seeded (no plays exist there yet -- the same state the recorder itself used), so this reproduces
    the recorder's own conditions as closely as this repo can get without a live model call."""
    play = rec.play
    reasons: list[str] = []

    schema_errors = [f"{'/'.join(str(p) for p in e.path) or '$'}: {e.message}" for e in sorted(pt._VALIDATOR.iter_errors(play), key=lambda e: list(e.path))]
    reasons.extend(f"schema: {m}" for m in schema_errors)
    try:
        Play.model_validate(play)
    except Exception as e:  # pydantic drift is a real validation failure, not a crash
        reasons.append(f"model: {e}")
    if reasons:
        return False, reasons  # the rest below assumes a structurally sound play

    ctx = PlannerContext.build(data_dir, run_id=rec.run_summary.get("run_id") or rec.tag, policy_version=play.get("policy_version"))
    token = set_context(ctx)
    try:
        try:
            gap = pt._gap(ctx, play["gap_id"])
        except KeyError as e:
            return False, [f"unknown gap {e}"]

        guardrail_check = check_guardrails(play, pt._guardrail_context(ctx, play))
        if not guardrail_check["all_passed"]:
            reasons.append("guardrails fail on re-check: " + "; ".join(f"{r['rule']}: {r['detail']}" for r in guardrail_check["results"] if not r["passed"]))
        if guardrail_check["results"] != play.get("guardrails"):
            reasons.append("recomputed guardrail results (rule, passed, detail) differ from the play's own recorded guardrails field")

        product = pt._product(ctx, play["target"]["sku"])
        partner = ctx.products.get((play.get("mechanic_params") or {}).get("bundle_sku") or "", {})
        money_mismatches = check_play_money(
            play, product.unit_cost, product.list_price, int(gap["units_at_risk"]),
            bundle_partner_unit_cost=float(partner.get("unit_cost") or 0.0), bundle_partner_list_price=float(partner.get("list_price") or 0.0),
            transfer_cost_per_unit=float(ctx.tenant.thresholds.get("transfer_cost_per_unit_inr", 2.0)),
        )
        reasons.extend(f"money invariant: {m}" for m in money_mismatches)

        est = estimate(play, pt._estimator_context(ctx, play))
        reasons.extend(f"expected_outcome.{m}" for m in _numeric_mismatches(play.get("expected_outcome") or {}, est["expected_outcome"]))
        reasons.extend(f"counterfactuals.{m}" for m in _numeric_mismatches(play.get("counterfactuals") or {}, est["counterfactuals"]))

        eo, target = play.get("expected_outcome") or {}, play.get("target") or {}
        units, target_units, units_at_risk = eo.get("units"), target.get("units"), gap["units_at_risk"]
        in_order = isinstance(units, int | float) and not isinstance(units, bool) and isinstance(target_units, int | float) and not isinstance(target_units, bool) and 0 < units <= target_units <= units_at_risk
        if not in_order:
            reasons.append(f"sanity: expected 0 < expected_outcome.units ({units!r}) <= target.units ({target_units!r}) <= gap.units_at_risk ({units_at_risk!r})")
        audience, holdout = play.get("audience") or {}, play.get("holdout") or {}
        treated = float(audience.get("size_after_consent", 0)) * (1 - float(holdout.get("fraction", 0)))
        min_treated = holdout.get("min_treated_n")
        if not (isinstance(min_treated, int) and not isinstance(min_treated, bool) and treated >= min_treated):
            reasons.append(f"sanity: audience.size_after_consent*(1-holdout.fraction)={treated:.2f} < holdout.min_treated_n={min_treated!r}")
    finally:
        reset_context(token)

    return (not reasons), reasons


def select_best(data_dir: str | Path, gap_id: str, candidates: list[Recording]) -> tuple[Recording | None, dict[str, list[str]]]:
    """Among `candidates` (already filtered by discover_candidates), the highest
    expected_outcome.margin_inr that validates; an exact tie goes to whichever comes first in
    `candidates`' own order (see discover_candidates: newest directory, then ascending run index).
    Deterministic: iterating in that fixed order and only replacing the incumbent on a STRICTLY
    greater margin is what makes a tie resolve to the earliest one. Returns (winner_or_None, a
    {candidate.tag: reasons} map for every candidate that failed validation)."""
    best: Recording | None = None
    best_margin: float | None = None
    failures: dict[str, list[str]] = {}
    for cand in candidates:
        ok, reasons = validate_recording(data_dir, cand)
        if not ok:
            failures[cand.tag] = reasons
            continue
        margin = float(cand.play.get("expected_outcome", {}).get("margin_inr", float("-inf")))
        if best is None or margin > best_margin:
            best, best_margin = cand, margin
    return best, failures


# --------------------------------------------------------------------------------------- seeding

def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _recorded_in(recording_dir: Path) -> str:
    try:
        return str(recording_dir.relative_to(ROOT))
    except ValueError:
        return str(recording_dir)  # outside the repo (e.g. a test's own tmp_path root)


def _seeded_trace_text(rec: Recording, new_source: str) -> str:
    """`rec.trace_text` verbatim except its one `kind: run_summary` record (agents/planner/run.py
    guarantees every trace ends with exactly one), which gets the new provenance fields. Every
    other line is passed through untouched, not round-tripped through json.loads/dumps, so nothing
    about it -- key order, number formatting -- can drift from what was actually recorded."""
    lines = rec.trace_text.splitlines()
    records = [json.loads(line) for line in lines if line.strip()]
    if not records:
        raise ValueError(f"{rec.tag}: recorded trace.jsonl has no events")
    recorded_at = _iso(records[0]["timestamp"]) if records[0].get("timestamp") else None
    recorded_in = _recorded_in(rec.dir)
    out_lines: list[str] = []
    seen_summary = False
    for line in lines:
        if not line.strip():
            continue
        rec_line = json.loads(line)
        if rec_line.get("kind") == "run_summary":
            rec_line = {**rec_line, "recorded_source": rec_line.get("source"), "source": new_source, "recorded_at": recorded_at, "recorded_in": recorded_in}
            line = json.dumps(rec_line, ensure_ascii=False)
            seen_summary = True
        out_lines.append(line)
    if not seen_summary:
        raise ValueError(f"{rec.tag}: recorded trace.jsonl has no run_summary record")
    return "\n".join(out_lines) + "\n"


def _seed_recording(data_dir: str | Path, rec: Recording) -> dict[str, Any]:
    """Write `rec`'s play (source rewritten to "recorded_gemini") and its trace into the store at
    `data_dir` -- no model call, no network: everything here is a local file write."""
    store = LocalStore(data_dir)
    play = dict(rec.play)
    play["source"] = "recorded_gemini"
    ctx = PlannerContext.build(data_dir, run_id=rec.run_summary.get("run_id") or rec.tag, policy_version=play.get("policy_version"))
    store.upsert("plays", "play_id", pt.play_row(ctx, play))

    run_id = play["trace_ref"].split("/", 1)[1]
    (store.root / "events" / f"{run_id}.jsonl").write_text(_seeded_trace_text(rec, play["source"]), encoding="utf-8")

    return {
        "run_id": run_id, "play": play, "status": "proposed", "iterations": rec.result.get("iterations", 0),
        "events": store.read_events(run_id), "policy_version": play.get("policy_version"),
        "source": "recorded_gemini", "planner_source": "model", "fallback_reason": None,
    }


def seed_from_recording(data_dir: str | Path, gap_id: str, raw_root: Path | str | None = None) -> tuple[dict[str, Any] | None, str]:
    """The whole discover -> validate -> select -> seed pipeline for `gap_id`. Returns (result,
    message): `result` is the seeded play's result dict (run_planner_async's own shape) when a
    committed recording validated and was seeded, else None -- the caller (harness/seed_plays.py)
    then runs the scripted stub exactly as it would have without this module. `message` is always
    one line: what got seeded, or why nothing did (no recording committed at all, vs. one or more
    found but none validating, with every candidate's reasons)."""
    root = raw_root if raw_root is not None else RAW_ROOT_DEFAULT
    candidates = discover_candidates(gap_id, root)
    if not candidates:
        return None, f"{gap_id}: no committed recording found under {root} -- seeding the scripted stub instead"

    best, failures = select_best(data_dir, gap_id, candidates)
    if best is None:
        detail = " | ".join(f"{tag}: {'; '.join(reasons)}" for tag, reasons in failures.items())
        return None, f"{gap_id}: {len(candidates)} committed recording(s) found but none validated against the current tenant ({detail}) -- seeding the scripted stub instead"

    result = _seed_recording(data_dir, best)
    margin = result["play"]["expected_outcome"]["margin_inr"]
    return result, f"{gap_id}: seeded from committed recording {best.tag} (source=recorded_gemini, margin_inr={margin:.2f}, {len(candidates) - 1} other candidate(s) considered)"
