"""Sealed decision-quality eval: run the real planner on the frozen scenarios and score it against the oracle.

    make eval-sealed                                    # stub backend, plumbing check only, $0
    TAAL_MODEL_BACKEND=vertex GOOGLE_CLOUD_PROJECT=... GOOGLE_APPLICATION_CREDENTIALS=... \\
        python -m harness.sealed_eval --out eval/raw/sealed_<date> --cap-usd 10

Protocol: eval/sealed/PROTOCOL.md. Scenarios: eval/sealed/scenarios.json; baselines (blanket 20%, do nothing, estimator upper bound): eval/sealed/baselines.json.
Each scenario runs once through `agents.planner.run.run_planner_async` on its own copy-on-write sandbox of the
scenario's tenant, as the product runs it. The spend ledger, the SDK tap and the INVALID rule are the ones of
harness/adversarial_eval.py (imported, not changed). Scenarios run `--concurrency` at a time (default 4); the cap is
kept safe by reserving each run's estimate before it starts.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from harness import adversarial_eval as ae
from harness.checklists import ROOT

SCEN = ROOT / "eval" / "sealed" / "scenarios.json"
ANSWERS = ROOT / "eval" / "sealed" / "baselines.json"
DATA_ROOT = ROOT / ".local" / "sealed"
RESERVE_USD = 0.30  # per planner run; the measured mean is $0.078 (eval/raw/live_eval_2026-10-14/summary.json)
DEADLINE_S = 120.0
TAAL_NOW = "2026-09-12T03:30:00Z"


class Reserver:
    """Cap safety under concurrency: a run starts only if spent + reserved by runs in flight + its own reserve fits the cap."""

    def __init__(self, ledger: ae.Ledger | None, cap: float, reserve: float):
        self.ledger, self.cap, self.reserve = ledger, cap, reserve
        self.reserved = 0.0
        self.lock = threading.Lock()

    def try_start(self) -> bool:
        if self.ledger is None:
            return True
        with self.lock:
            if self.ledger.stopped or self.ledger.spent + self.reserved + self.reserve > self.cap:
                return False
            self.reserved += self.reserve
            return True

    def release(self) -> None:
        if self.ledger is None:
            return
        with self.lock:
            self.reserved = max(0.0, self.reserved - self.reserve)


def prompt_version() -> str:
    """Top entry of agents/planner/prompts/CHANGELOG.md (v7 for the first sealed eval, v8 with the markdown option)."""
    import re

    m = re.search(r"^- (v\d+)\b", (ROOT / "agents/planner/prompts/CHANGELOG.md").read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else "unknown"


def recovery_of_play(play: dict[str, Any]) -> float:
    cf = play["counterfactuals"]
    return round(float(cf["do_nothing_inr"]) + float(cf["play_net_inr"]), 2)


async def one_run(sc: dict[str, Any], ans: dict[str, Any], ctx: dict[str, Any], ledger: ae.Ledger | None, attempt: int) -> dict[str, Any]:
    from agents.planner.run import run_planner_async
    from eval.sealed.make_scenarios import ensure_tenant
    from harness.record_planner_traces import sandbox

    tag = f"{sc['scenario_id']}__run{attempt + 1}"
    ae.RUN_TAG.set(tag)
    t0 = time.time()
    rec: dict[str, Any] = {"scenario_id": sc["scenario_id"], "cell": sc["cell"], "gap_id": sc["gap"]["gap_id"], "seed": sc["seed"], "attempt": attempt, "started_at": ae.now_utc(), "tag": tag}
    work = ctx["tmp"] / tag
    try:
        base = await asyncio.to_thread(ensure_tenant, ctx["data_root"], sc["seed"])
        store = await asyncio.to_thread(sandbox, base, work)
        records: list[dict[str, Any]] = []

        def on_event(kind: str, obj: Any) -> None:
            d = obj.model_dump(mode="json", exclude_none=True) if hasattr(obj, "model_dump") else obj
            records.append({"kind": "user", "content": d} if kind == "user" else {"kind": "event", "event": d})

        out = await run_planner_async(store.root, sc["gap"]["gap_id"], backend=ctx["backend"], deadline_s=DEADLINE_S, on_event=on_event)
        play = out.get("play")
        if play:
            rows = store.find("plays", play_id=play["play_id"])
            play = json.loads(rows[-1]["play_json"]) if rows else play
        drafts, texts, verdicts = ae.extract_drafts(records)
        fb = str(out.get("fallback_reason") or "")
        timeout_or_infra = fb.startswith("deadline exceeded") or fb.startswith("model unavailable")
        model_play = play if (play and out.get("planner_source") == "model" and out.get("status") == "proposed") else None
        audit = await asyncio.to_thread(ae.audit_final_play, store, model_play) if model_play else {}
        guardrail_violation = bool(model_play) and not (audit.get("guardrails_all_passed") and not audit.get("money_mismatches") and audit.get("holdout_ok") and audit.get("beats_markdown_ok", True))
        events = out.get("events") or []
        summary = next((e for e in reversed(events) if e.get("kind") == "run_summary"), {})
        rec.update({
            "status": "proposed" if model_play else "no_play", "outcome": "model_play" if model_play else ("deterministic_fallback" if play else "no_play"), "planner_status": out.get("status"), "planner_source": out.get("planner_source"), "source": out.get("source"),
            "fallback_reason": out.get("fallback_reason"), "accepted_play": model_play, "deterministic_fallback_play": play if (play and not model_play) else None,
            "recovery_inr": recovery_of_play(model_play) if model_play else 0.0, "mechanic": model_play["mechanic"] if model_play else None,
            "drafts": drafts, "model_texts": texts, "propose_play_verdicts": verdicts,
            "first_proposal_accepted": bool(verdicts) and bool(verdicts[0]["valid"]), "propose_play_attempts": len(verdicts),
            "iterations": out.get("iterations"), "elapsed_ms": out.get("elapsed_ms"), "audit": audit, "guardrail_violation_at_approve": guardrail_violation,
            "run_summary": {k: summary.get(k) for k in ("run_id", "status", "iterations", "elapsed_ms", "usage", "model", "backend", "source")},
            "baselines": {"oracle_upper_bound_inr": ans["oracle_upper_bound_inr"], "blanket20_recovery_inr": ans["blanket20_recovery_inr"], "do_nothing_recovery_inr": 0.0},
            "verdict": "VALID",
        })
        if timeout_or_infra:
            rec.update({"verdict": "INVALID", "reason": f"timeout or infra: {fb}"})
    except ae.SpendCapReached as e:
        rec.update({"verdict": "NOT_RUN", "reason": f"spend cap: {e}"})
    except BaseException as e:  # noqa: BLE001 -- a crashed run is a recorded outcome
        if ledger is not None and ledger.stopped:
            rec.update({"verdict": "NOT_RUN", "reason": "spend cap reached during the run"})
        else:
            rec.update({"verdict": "INVALID", "reason": f"infra/harness error {type(e).__name__}: {str(e)[:300]}", "traceback": traceback.format_exc()[-3000:]})
    finally:
        shutil.rmtree(work, ignore_errors=True)
    rec["wall_s"] = round(time.time() - t0, 1)
    if ledger is not None:
        calls = ledger.calls_for(tag)
        rec["model_calls"] = [{k: c.get(k) for k in ("requested_model", "model_version", "usage", "usd", "error", "elapsed_s", "thinking_level")} for c in calls]
        rec["usd"] = round(sum(c.get("usd", 0.0) for c in calls), 6)
        rec["tokens"] = {k: sum((c["usage"] or {}).get(k, 0) for c in calls) for k in ("prompt", "cached", "candidates", "thoughts")}
        rec["models_requested"] = sorted({c["requested_model"] for c in calls if c["requested_model"]})
        rec["model_versions_reported"] = sorted({str(c["model_version"]) for c in calls if c["usage"]})
        bad = ledger.invalid_reasons(tag)
        if bad and rec["verdict"] != "NOT_RUN":
            rec["verdict_before_invalidation"] = rec["verdict"]
            rec.update({"verdict": "INVALID", "reason": "; ".join(sorted(set(bad)))})
    else:
        u = (rec.get("run_summary") or {}).get("usage") or {}
        rec["usd"] = 0.0
        rec["tokens"] = {"prompt": u.get("prompt_token_count", 0), "cached": u.get("cached_content_token_count", 0), "candidates": u.get("candidates_token_count", 0), "thoughts": u.get("thoughts_token_count", 0)}
        rec["models_requested"] = rec["model_versions_reported"] = [ctx["backend"]]
    return rec


async def execute(scenarios: list[dict[str, Any]], answers: dict[str, Any], ctx: dict[str, Any], ledger: ae.Ledger | None, reserver: Reserver, out_dir: Path, concurrency: int) -> None:
    sem = asyncio.Semaphore(concurrency)
    raw = out_dir / "runs"
    raw.mkdir(parents=True, exist_ok=True)

    async def guarded(sc: dict[str, Any]) -> None:
        async with sem:
            sid = sc["scenario_id"]
            if not reserver.try_start():
                rec = {"scenario_id": sid, "cell": sc["cell"], "gap_id": sc["gap"]["gap_id"], "attempt": 0, "verdict": "NOT_RUN", "reason": f"spend cap: spent {ledger.spent:.4f} + reserved {reserver.reserved:.2f} + reserve {reserver.reserve} would pass {reserver.cap}" if ledger else "not run"}
                (raw / f"{sid}.json").write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8")
                print(f"  {sid} NOT_RUN", flush=True)
                return
            try:
                first = await one_run(sc, answers[sid], ctx, ledger, 0)
            finally:
                reserver.release()
            rec = first
            if first["verdict"] == "INVALID":
                (raw / f"{sid}__attempt0_invalid.json").write_text(json.dumps(first, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
                if reserver.try_start():
                    try:
                        again = await one_run(sc, answers[sid], ctx, ledger, 1)
                    finally:
                        reserver.release()
                    again["first_attempt"] = {k: first.get(k) for k in ("verdict", "reason", "tag", "usd")}
                    rec = again
            (raw / f"{sid}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
            print(f"  {sid} {rec['verdict']:8s} {str(rec.get('mechanic')):20s} recovery {rec.get('recovery_inr')} / upper bound {answers[sid]['oracle_upper_bound_inr']}" + (f"  ${ledger.spent:.3f}" if ledger else ""), flush=True)

    await asyncio.gather(*(guarded(sc) for sc in scenarios))


# ----------------------------------------------------------------------------- metrics

def pct(xs: list[float], q: float) -> float:
    s = sorted(xs)
    if not s:
        return float("nan")
    k = (len(s) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def compute_metrics(scenarios: list[dict[str, Any]], answers: dict[str, Any], runs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Primary: beats blanket 20% and beats doing nothing. A fallback play or no play never beats either baseline."""
    valid = [(sc, runs[sc["scenario_id"]]) for sc in scenarios if runs.get(sc["scenario_id"], {}).get("verdict") == "VALID"]
    excluded = [{"scenario_id": sc["scenario_id"], "verdict": runs.get(sc["scenario_id"], {}).get("verdict", "NOT_RUN"), "reason": runs.get(sc["scenario_id"], {}).get("reason")} for sc in scenarios if runs.get(sc["scenario_id"], {}).get("verdict") != "VALID"]
    n = len(valid)
    rows = []
    for sc, r in valid:
        a = answers[sc["scenario_id"]]
        model_play = r["outcome"] == "model_play"
        got = r["recovery_inr"] if model_play else 0.0
        ub = a["oracle_upper_bound_inr"]
        rows.append({
            "scenario_id": sc["scenario_id"], "gap_type": sc["gap"]["type"], "outcome": r["outcome"], "mechanic": r["mechanic"], "recovery_inr": got, "blanket20_recovery_inr": a["blanket20_recovery_inr"], "upper_bound_inr": ub,
            "beats_blanket": model_play and got > a["blanket20_recovery_inr"], "beats_do_nothing": model_play and got > 0.0, "beat_over_blanket_inr": round(got - a["blanket20_recovery_inr"], 2),
            "captured": (got / ub) if ub > 0 else None, "first_proposal_accepted": r["first_proposal_accepted"], "iterations": r["iterations"], "guardrail_violation": r["guardrail_violation_at_approve"], "elapsed_s": (r["elapsed_ms"] or 0) / 1000.0, "usd": r["usd"],
        })
    cap = [x["captured"] for x in rows if x["captured"] is not None]
    lat = [x["elapsed_s"] for x in rows]
    usd = [x["usd"] for x in rows]
    mix: dict[str, int] = {}
    for x in rows:
        if x["outcome"] == "model_play":
            mix[x["mechanic"]] = mix.get(x["mechanic"], 0) + 1
    beating = [x for x in rows if x["beats_blanket"]]
    v2: dict[str, Any] = {}
    extra: dict[str, Any] = {}
    if any("blanket_legal_recovery_inr" in a for a in answers.values()):
        legal = {sc["scenario_id"]: answers[sc["scenario_id"]] for sc, _ in valid}
        for x in rows:
            a = legal[x["scenario_id"]]
            x["beats_legal_blanket"] = x["outcome"] == "model_play" and x["recovery_inr"] > a["blanket_legal_recovery_inr"]
            x["ceiling_beats_blanket20"] = bool(a["upper_bound_beats_blanket20"])
        ceil = [x for x in rows if x["ceiling_beats_blanket20"]]
        extra["v3"] = {
            "beats_legal_blanket": {"n": sum(x["beats_legal_blanket"] for x in rows), "of": n},
            "ceiling_scenarios_where_a_legal_play_can_beat_blanket20": len(ceil),
            "ceiling_scenarios_beaten": sum(1 for x in ceil if x["beats_blanket"]),
            "blanket20_floor_illegal_scenarios": sum(1 for sc, _ in valid if not answers[sc["scenario_id"]]["blanket20_is_floor_legal"]),
            "valid_runs": n, "mean_model_calls": statistics.mean(len(r.get("model_calls") or []) for _, r in valid) if valid else None,
            "mean_prompt_tokens": statistics.mean(r["tokens"]["prompt"] for _, r in valid) if valid else None,
        }
    if any("markdown_is_best_baseline" in a for a in answers.values()):
        flagged = [(sc, x) for sc, x in zip((sc for sc, _ in valid), rows, strict=True) if answers[sc["scenario_id"]].get("markdown_is_best_baseline")]
        md_all = [x for x in rows if x["outcome"] == "model_play" and x["mechanic"] == "markdown"]
        best_bl = {sc["scenario_id"]: answers[sc["scenario_id"]].get("best_blanket_recovery_inr") for sc, _ in valid}
        v2.update({
            "markdown_chosen_where_best_baseline_is_markdown": {"n": sum(1 for _, x in flagged if x["outcome"] == "model_play" and x["mechanic"] == "markdown"), "of": len(flagged)},
            "markdown_chosen_total": len(md_all),
            "net_over_best_blanket_inr_all_scenarios": round(sum(x["recovery_inr"] - (best_bl[x["scenario_id"]] or 0.0) for x in rows), 2),
            "by_stratum": {st: {"n": sum(1 for sc, _ in valid if answers[sc["scenario_id"]].get("stratum") == st), "beats_blanket": sum(1 for (sc, _), x in zip(valid, rows, strict=True) if answers[sc["scenario_id"]].get("stratum") == st and x["beats_blanket"]),
                                "net_over_blanket20_inr": round(sum(x["beat_over_blanket_inr"] for (sc, _), x in zip(valid, rows, strict=True) if answers[sc["scenario_id"]].get("stratum") == st), 2)}
                           for st in sorted({a.get("stratum") for a in answers.values() if a.get("stratum")})},
        })
    # v4 metrics (turns, tokens, net vs max(0, blanket), beats-blanket against the ceiling); reported for every set of files
    n_turns = [len(r.get("model_calls") or []) for _, r in valid]
    extra["v4"] = {
        "model_turns_per_run": {"mean": statistics.mean(n_turns) if n_turns else None, "median": statistics.median(n_turns) if n_turns else None, "max": max(n_turns) if n_turns else None},
        "prompt_tokens_per_run_mean": statistics.mean((r.get("tokens") or {}).get("prompt", 0) for _, r in valid) if valid else None,
        "output_tokens_per_run_mean": statistics.mean((r.get("tokens") or {}).get("candidates", 0) + (r.get("tokens") or {}).get("thoughts", 0) for _, r in valid) if valid else None,
        "net_over_blanket20_raw_inr": round(sum(x["beat_over_blanket_inr"] for x in rows), 2),
        "net_over_max0_blanket20_inr": round(sum(x["recovery_inr"] - max(0.0, x["blanket20_recovery_inr"]) for x in rows), 2),
        "beats_blanket20_all": {"n": len(beating), "of": n},
        "ceiling_beats_blanket20": {"scenarios": sum(1 for sc, _ in valid if answers[sc["scenario_id"]].get("upper_bound_beats_blanket20", answers[sc["scenario_id"]]["oracle_upper_bound_inr"] > answers[sc["scenario_id"]]["blanket20_recovery_inr"])),
                                     "beaten": sum(1 for (sc, _), x in zip(valid, rows, strict=True) if x["beats_blanket"] and answers[sc["scenario_id"]].get("upper_bound_beats_blanket20", answers[sc["scenario_id"]]["oracle_upper_bound_inr"] > answers[sc["scenario_id"]]["blanket20_recovery_inr"]))},
        "first_result_turn_count_distribution": {str(k): n_turns.count(k) for k in sorted(set(n_turns))},
    }
    return {
        **v2, **extra,
        "scenarios": len(scenarios), "valid": n, "excluded": excluded,
        "beats_blanket20": {"n": len(beating), "of": n, "total_beat_inr_where_beaten": round(sum(x["beat_over_blanket_inr"] for x in beating), 2), "net_over_blanket_inr_all_scenarios": round(sum(x["beat_over_blanket_inr"] for x in rows), 2)},
        "beats_do_nothing": {"n": sum(x["beats_do_nothing"] for x in rows), "of": n},
        "guardrail_violations_reaching_approve": sum(bool(x["guardrail_violation"]) for x in rows),
        "outcomes": {k: sum(x["outcome"] == k for x in rows) for k in ("model_play", "deterministic_fallback", "no_play")},
        "first_proposal_accepted": {"n": sum(bool(x["first_proposal_accepted"]) for x in rows), "of": n}, "mean_iterations": statistics.mean([x["iterations"] or 0 for x in rows]) if rows else None,
        "latency_s": {"p50": pct(lat, 0.5) if lat else None, "p95": pct(lat, 0.95) if lat else None},
        "cost_usd": {"per_scenario_mean": statistics.mean(usd) if usd else None, "per_scenario_max": max(usd) if usd else None, "total": round(sum(usd), 4)},
        "mechanic_mix": mix,
        "estimator_upper_bound_secondary": {"captured_median": statistics.median(cap) if cap else None, "captured_p10": pct(cap, 0.10) if cap else None, "captured_min": min(cap) if cap else None, "n": len(cap)},
        "by_gap_type": {t: {"n": sum(x["gap_type"] == t for x in rows), "beats_blanket": sum(x["beats_blanket"] for x in rows if x["gap_type"] == t)} for t in sorted({x["gap_type"] for x in rows})},
        "rows": rows,
    }


def fmt(v: Any, nd: int = 3) -> str:
    return "n/a" if v is None else (f"{v:.{nd}f}" if isinstance(v, float) else str(v))


def write_summary(path: Path, meta: dict[str, Any], m: dict[str, Any]) -> None:
    ub = m["estimator_upper_bound_secondary"]
    L = [f"# Sealed decision-quality eval ({meta['date']})", "",
         f"Label: **{meta['label']}**. Model {meta['model']}, prompt {meta['prompt_version']}, {m['valid']} valid scenarios of {m['scenarios']}, concurrency {meta['concurrency']}, 1 run per scenario (plus one re-run of an INVALID run). Protocol: {meta.get('protocol', 'eval/sealed/PROTOCOL.md')}.", "",
         "Recovery is the projected recovery under Taal's own estimator (recovered versus doing nothing) on a synthetic tenant, not a real-world outcome. A fallback play or no play counts as not beating either baseline.", "",
         "| Metric | Result |", "|---|---|",
         f"| **PRIMARY: beats blanket 20% markdown** | **{m['beats_blanket20']['n']} of {m['beats_blanket20']['of']}**; rupees by which it beats it where it does INR {fmt(m['beats_blanket20']['total_beat_inr_where_beaten'], 2)} (net over all scenarios INR {fmt(m['beats_blanket20']['net_over_blanket_inr_all_scenarios'], 2)}) |",
         f"| Beats doing nothing | {m['beats_do_nothing']['n']} of {m['beats_do_nothing']['of']} |",
         f"| **HARD: guardrail violations reaching Approve (must be 0)** | **{m['guardrail_violations_reaching_approve']}** |",
         f"| Outcomes: model-authored play / deterministic fallback / no play | {m['outcomes']['model_play']} / {m['outcomes']['deterministic_fallback']} / {m['outcomes']['no_play']} |",
         f"| First proposal accepted by the gate; mean iterations | {m['first_proposal_accepted']['n']} of {m['first_proposal_accepted']['of']}; {fmt(m['mean_iterations'], 2)} |",
         f"| Latency p50 / p95 (s) | {fmt(m['latency_s']['p50'], 1)} / {fmt(m['latency_s']['p95'], 1)} |",
         f"| Cost per scenario (USD) mean / max; total spend | {fmt(m['cost_usd']['per_scenario_mean'], 4)} / {fmt(m['cost_usd']['per_scenario_max'], 4)}; {fmt(m['cost_usd']['total'], 4)} |",
         f"| Mechanic mix of accepted plays | {', '.join(f'{k} {v}' for k, v in sorted(m['mechanic_mix'].items())) or 'none'} |",
         f"| SECONDARY, estimator upper bound (not a best play): captured ratio median / p10 / min | {fmt(ub['captured_median'])} / {fmt(ub['captured_p10'])} / {fmt(ub['captured_min'])} (n={ub['n']}) |", "",
         ("The upper bound is the highest recovery among the candidates in the oracle's grid that pass every guardrail, scored by the same estimator. The estimator ignores discount depth and counts a bundle's full price per responding unit, so the bound favours a lowest-discount bundle; it is not an optimal or best-possible play." if "markdown_chosen_total" not in m else
          "The upper bound is the larger of the best allowed markdown play and the oracle's best legal non-markdown play (beats_markdown gate off), scored by the same est-v2 estimator; it is not an optimal or best-possible play."), "",
         ]
    if "markdown_chosen_total" in m:
        mw = m["markdown_chosen_where_best_baseline_is_markdown"]
        L += ["", "## Markdown option (v2 metrics)", "", "| Metric | Result |", "|---|---|",
              f"| **Chooses a markdown where the best baseline is a markdown** | **{mw['n']} of {mw['of']}** |",
              f"| Net rupees vs blanket 20% markdown, all scenarios | INR {fmt(m['beats_blanket20']['net_over_blanket_inr_all_scenarios'], 2)} |",
              f"| Net rupees vs the best blanket depth (10/20/35%), all scenarios | INR {fmt(m['net_over_best_blanket_inr_all_scenarios'], 2)} |",
              f"| Markdown chosen, all scenarios | {m['markdown_chosen_total']} |"]
        for st, v in m["by_stratum"].items():
            L.append(f"| Stratum {st}: n / beats blanket 20% / net vs blanket 20% | {v['n']} / {v['beats_blanket']} / INR {fmt(v['net_over_blanket20_inr'], 2)} |")
    if "v3" in m:
        v3 = m["v3"]
        L += ["", "## Legal-baseline view (v3 metrics)", "", "| Metric | Result |", "|---|---|",
              f"| Beats the best margin-floor-LEGAL blanket depth (0 if none is legal) | {v3['beats_legal_blanket']['n']} of {v3['beats_legal_blanket']['of']} |",
              f"| Blanket 20% is floor-illegal in | {v3['blanket20_floor_illegal_scenarios']} of {m['valid']} scenarios |",
              f"| Scenarios where the model-free upper bound exceeds blanket 20% (a legal play can beat it) | {v3['ceiling_scenarios_where_a_legal_play_can_beat_blanket20']} |",
              f"| Of those, beaten by the planner | {v3['ceiling_scenarios_beaten']} |",
              f"| Valid runs; mean model calls per run; mean prompt tokens per run | {v3['valid_runs']}; {fmt(v3['mean_model_calls'], 1)}; {fmt(v3['mean_prompt_tokens'], 0)} |"]
    if "v4" in m:
        v4 = m["v4"]
        L += ["", "## v4 metrics", "", "| Metric | Result |", "|---|---|",
              f"| Model turns per run: mean / median / max | {fmt(v4['model_turns_per_run']['mean'], 2)} / {fmt(v4['model_turns_per_run']['median'], 1)} / {v4['model_turns_per_run']['max']} |",
              f"| Prompt tokens per run (mean); output + thinking tokens per run (mean) | {fmt(v4['prompt_tokens_per_run_mean'], 0)}; {fmt(v4['output_tokens_per_run_mean'], 0)} |",
              f"| Beats blanket 20%, all valid | {v4['beats_blanket20_all']['n']} of {v4['beats_blanket20_all']['of']} |",
              f"| Beats blanket 20% against the ceiling (scenarios where a legal play can) | {v4['ceiling_beats_blanket20']['beaten']} of {v4['ceiling_beats_blanket20']['scenarios']} |",
              f"| Net vs blanket 20%, raw / with a loss-making blanket counted as 0 | INR {fmt(v4['net_over_blanket20_raw_inr'], 2)} / INR {fmt(v4['net_over_max0_blanket20_inr'], 2)} |",
              f"| Turn-count distribution | {v4['first_result_turn_count_distribution']} |"]
    L += ["", "## By gap type", "", "| Gap type | n | beats blanket |", "|---|---|---|"]
    for t, v in m["by_gap_type"].items():
        L.append(f"| {t} | {v['n']} | {v['beats_blanket']} |")
    L += ["", "## Per scenario", "", "| id | outcome | mechanic | recovery | blanket 20% | upper bound | beats blanket | iterations |", "|---|---|---|---|---|---|---|---|"]
    for x in m["rows"]:
        L.append(f"| {x['scenario_id']} | {x['outcome']} | {x['mechanic'] or '-'} | {fmt(x['recovery_inr'], 2)} | {fmt(x['blanket20_recovery_inr'], 2)} | {fmt(x['upper_bound_inr'], 2)} | {x['beats_blanket']} | {x['iterations']} |")
    if m["excluded"]:
        L += ["", "## Excluded (INVALID or NOT RUN), reported and not scored", ""] + [f"- {e['scenario_id']}: {e['verdict']}: {e['reason']}" for e in m["excluded"]]
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cap-usd", type=float, default=10.0)
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--retry-429", type=int, default=4, help="retry a 429 this many times with backoff before the SDK fails over to the fallback model (0 = off, the v1/v2 behaviour)")
    ap.add_argument("--backend", default=None)
    ap.add_argument("--scenarios", default=str(SCEN))
    ap.add_argument("--answers", default=str(ANSWERS))
    ap.add_argument("--data-root", default=str(DATA_ROOT))
    ap.add_argument("--protocol", default="eval/sealed/PROTOCOL.md")
    ap.add_argument("--only", default=None, help="comma-separated scenario ids")
    ap.add_argument("--thinking-route", default=None, help="override [thinking] planner_route for this run (dev experiments only)")
    ap.add_argument("--thinking-final", default=None, help="override [thinking] planner_final for this run (dev experiments only)")
    args = ap.parse_args(argv)

    from agents.gate.config import load_models

    os.environ.setdefault("TAAL_NOW", TAAL_NOW)
    models = load_models()
    backend = args.backend or models["backend"]
    live = backend == "vertex"
    if live and not (os.environ.get(models["vertex"]["project_env"]) and os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")):
        print("sealed_eval: vertex needs GOOGLE_CLOUD_PROJECT and GOOGLE_APPLICATION_CREDENTIALS; nothing run")
        return 1
    scen_doc = json.loads(Path(args.scenarios).read_text(encoding="utf-8"))
    answers = json.loads(Path(args.answers).read_text(encoding="utf-8"))["baselines"]
    scenarios = [s for s in scen_doc["scenarios"] if not args.only or s["scenario_id"] in set(args.only.split(","))]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.thinking_route or args.thinking_final:
        from agents.gate import config as gate_config

        real_load = gate_config.load_models

        def patched_models():
            m = real_load()
            m["thinking"] = {**m.get("thinking", {}), **({"planner_route": args.thinking_route} if args.thinking_route else {}), **({"planner_final": args.thinking_final} if args.thinking_final else {})}
            return m

        for mod_name in ("agents.gate.config", "agents.planner.agent", "agents.planner.run", "harness.sealed_eval"):
            mod = sys.modules.get(mod_name) or __import__(mod_name, fromlist=["x"])
            if hasattr(mod, "load_models"):
                mod.load_models = patched_models
        models = patched_models()
    if args.retry_429 > 0:
        from agents import vertex_models

        vertex_models.LIVE_429_BACKOFF_S = ()  # the harness backs off at the SDK; no second layer
    ledger = ae.Ledger(args.cap_usd, models["ids"]["flash"], models["pricing"], out_dir / "model_calls.jsonl") if live else None
    if ledger:
        ae.RETRY_429 = max(0, args.retry_429)
        ae.install_tap(ledger)
    reserver = Reserver(ledger, args.cap_usd, RESERVE_USD)
    started = time.time()
    from eval.sealed.make_scenarios import ensure_tenant

    for seed in sorted({s["seed"] for s in scenarios}):  # build each tenant once, before the runs start (concurrent first builds raced in the v2 regression)
        ensure_tenant(Path(args.data_root), seed)
    with tempfile.TemporaryDirectory(prefix="taal_sealed_") as work:
        ctx = {"tmp": Path(work), "backend": backend, "data_root": Path(args.data_root)}
        asyncio.run(execute(scenarios, answers, ctx, ledger, reserver, out_dir, args.concurrency))
    runs = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((out_dir / "runs").glob("[SD][0-9][0-9].json"))}
    m = compute_metrics(scenarios, answers, runs)
    meta = {
        "date": datetime.now(UTC).date().isoformat(), "run_at": ae.now_utc(), "backend": backend, "model": models["ids"]["flash"] if live else "stub-planner", "prompt_version": prompt_version(), "protocol": args.protocol,
        "label": "measured" if live else "stub plumbing check (scripted stand-in, NOT the model; numbers are not results)", "concurrency": args.concurrency, "retry_429": args.retry_429 if live else 0, "cap_usd": args.cap_usd, "reserve_usd_per_run": RESERVE_USD,
        "planner_deadline_s": DEADLINE_S, "thinking": models.get("thinking"), "wall_s": round(time.time() - started, 1),
        "git_head": subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
        "preregistration_commit": os.environ.get("SEALED_PREREG_COMMIT") or subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
        "scenarios_sha256": ae.sha256_file(Path(args.scenarios)), "baselines_sha256": ae.sha256_file(Path(args.answers)),
        "planner_prompt_sha256": ae.sha256_file(ROOT / "agents/planner/prompts/planner.md"), 
        "spent_usd": round(ledger.spent, 4) if ledger else 0.0, "model_calls": len(ledger.calls) if ledger else 0,
        "max_calls_in_flight": ledger.max_inflight if ledger else 0,
    }
    (out_dir / "results.json").write_text(json.dumps({"meta": meta, "metrics": m}, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    if ledger:
        doc = {"model": meta["model"], "cap_usd": args.cap_usd, "total_usd": round(ledger.spent, 4), "model_calls": len(ledger.calls), "failed_calls": sum(1 for c in ledger.calls if c["error"]), "max_calls_in_flight": ledger.max_inflight,
               "calls_by_requested_model": {k: sum(1 for c in ledger.calls if c["requested_model"] == k) for k in sorted({c["requested_model"] for c in ledger.calls})},
               "calls_by_model_version_reported": {k: sum(1 for c in ledger.calls if c["usage"] and str(c["model_version"]) == k) for k in sorted({str(c["model_version"]) for c in ledger.calls if c["usage"]})},
               "source": "usage_metadata of each response via the tap in harness/adversarial_eval.py; list prices from config/models.toml [pricing]"}
        (out_dir / "spend_ledger.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    else:
        (out_dir / "spend_ledger.json").write_text(json.dumps({"backend": backend, "total_usd": 0.0, "model_calls": 0, "note": "stub backend: no model call is made"}, indent=1) + "\n", encoding="utf-8")
    write_summary(out_dir / "summary.md", meta, m)
    print(f"valid {m['valid']}/{m['scenarios']}; spend ${meta['spent_usd']}; guardrail violations at Approve: {m['guardrail_violations_reaching_approve']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
