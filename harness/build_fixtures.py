"""Rebuild the committed fixtures from the generated tenant (deterministic; run after `make generate`).

    python -m harness.build_fixtures

Writes: fixtures/plays/valid/*.json (20 golden plays from the stub planner), fixtures/plays/invalid/*.json
(20 mutations, each with the mutation named), fixtures/golden_runs/*.jsonl (planner traces for the demo
gaps under policy v1 and v2, the chips approve response, Meena's conversation), agents/planner/evalsets/*.evalset.json
(ADK evalset format, tool trajectories from the recorded runs), fixtures/demo_snapshot.json.

Evalsets come from real recorded model runs when a committed vertex trace directory exists
(eval/raw/planner_traces_<date>/, written by harness/record_planner_traces.py): one evalset per
recorded gap, expected trajectory = the recorded tool names in order, plus
agents/planner/evalsets/test_config.json with the criteria. Without one, the five stub-run evalsets
are written as before. Rebuild only the evalsets:

    python -m harness.build_fixtures --evalsets-from-traces eval/raw/planner_traces_<date>
"""
from __future__ import annotations

import asyncio
import copy
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

from agents.customer.chat import reset_sessions, run_chat_async
from agents.gate.config import load_tenant
from agents.gate.store import LocalStore, OverlayStore
from agents.planner.run import run_planner_async
from harness.checklists import ROOT
from jobs.measure.run import run_measure
from services.api.approve import approve

FIX = ROOT / "fixtures"
POLICY_V2 = FIX / "policy_v2.txt"
DEMO_GAPS = ["gap_chips_ds07", "gap_tea_ds04", "gap_cola_ds07", "gap_cola_ds02", "gap_kaju_ds01", "gap_kaju_ds03", "gap_quinoa_out02"]
FIXED_NOW = datetime(2026, 9, 12, 9, 0, tzinfo=UTC)

# ---------------------------------------------------------------------- stylist photo fixtures
# 16x16 solid-colour PNG swatches (no third-party image library, ~100 bytes each) standing in for
# staged garment and selfie photos, in the fixtures/photos/pallet_0N.json style: what the stub
# vision backend returns for each is the paired *.json, hand-checked, not the pixel data itself.
_GARMENT_SWATCHES: dict[str, tuple[tuple[int, int, int], dict]] = {
    "mustard_kurta": ((212, 160, 23), {"garment_type": "kurta", "colour": "mustard", "pattern": "solid", "fabric": "cotton", "confidence": 0.92}),
    "navy_tshirt": ((31, 42, 68), {"garment_type": "t-shirt", "colour": "navy", "pattern": "solid", "fabric": "cotton", "confidence": 0.88}),
    "red_floral_dress": ((178, 34, 34), {"garment_type": "dress", "colour": "red", "pattern": "floral", "fabric": "crepe", "confidence": 0.62}),
}
_SELFIE_SWATCHES: dict[str, tuple[tuple[int, int, int], dict]] = {
    "warm_medium": ((201, 152, 105), {"undertone": "warm", "depth": "medium", "confidence": 0.82}),
    "cool_light": ((234, 202, 187), {"undertone": "cool", "depth": "light", "confidence": 0.78}),
    "unclear": ((128, 128, 128), {"undertone": None, "depth": None, "confidence": 0.30}),
}


def _write_png(path: Path, rgb: tuple[int, int, int], size: int = 16) -> None:
    """A minimal, valid, uncompressed-content PNG: one IHDR (8-bit RGB), one IDAT (each scanline
    filter-type 0 followed by size*3 solid-colour bytes), one IEND. No Pillow/numpy dependency."""
    import struct
    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes(rgb) * size for _ in range(size))
    idat = zlib.compress(raw, 9)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def _write_garment_swatches() -> int:
    n = 0
    for name, (rgb, attrs) in _GARMENT_SWATCHES.items():
        _write_png(FIX / "photos" / "garments" / f"{name}.png", rgb)
        _write(FIX / "photos" / "garments" / f"{name}.json", attrs)
        n += 1
    for name, (rgb, attrs) in _SELFIE_SWATCHES.items():
        _write_png(FIX / "photos" / "selfies" / f"{name}.png", rgb)
        _write(FIX / "photos" / "selfies" / f"{name}.json", attrs)
        n += 1
    return n



def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=False) + "\n", encoding="utf-8")


def mutations(play: dict) -> list[tuple[str, dict]]:
    out = []

    def mut(name, fn):
        p = copy.deepcopy(play)
        fn(p)
        out.append((name, p))

    mut("holdout_fraction_below_0.05", lambda p: p["holdout"].__setitem__("fraction", 0.01))
    mut("missing_citations", lambda p: p.pop("citations"))
    mut("negative_units", lambda p: p["target"].__setitem__("units", -5))
    mut("zero_units", lambda p: p["target"].__setitem__("units", 0))
    mut("unknown_mechanic", lambda p: p.__setitem__("mechanic", "flash_sale"))
    mut("bad_play_id", lambda p: p.__setitem__("play_id", "chips_ds07"))
    mut("bad_gap_id", lambda p: p.__setitem__("gap_id", "chips_ds07"))
    mut("empty_node_ids", lambda p: p["target"].__setitem__("node_ids", []))
    mut("audience_purpose_not_marketing", lambda p: p["audience"].__setitem__("purpose", "analytics"))
    mut("unknown_guardrail_rule", lambda p: p["guardrails"].append({"rule": "be_nice", "passed": True, "detail": ""}))
    mut("guardrail_missing_detail", lambda p: p["guardrails"].__setitem__(0, {"rule": "margin_floor", "passed": True}))
    mut("extra_top_level_field", lambda p: p.__setitem__("llm_confidence", 0.9))
    mut("rationale_empty", lambda p: p.__setitem__("rationale", ""))
    mut("status_unknown", lambda p: p.__setitem__("status", "live"))
    mut("discount_over_100", lambda p: p["mechanic_params"].__setitem__("discount_pct", 150))
    mut("ci_low_negative", lambda p: p["expected_outcome"].__setitem__("ci_low", -1))
    mut("four_alternatives", lambda p: p.__setitem__("alternatives", [p["alternatives"][0] if p["alternatives"] else {"mechanic": "coupon", "mechanic_params": {}, "expected_units": 1, "expected_margin_inr": 1, "rejected_because": "x"}] * 4))
    mut("copy_language_not_iso", lambda p: p["copy"].__setitem__("language_set", ["english"]))
    mut("missing_expected_outcome", lambda p: p.pop("expected_outcome"))
    mut("seed_too_short", lambda p: p["holdout"].__setitem__("seed", "ab"))
    mut("window_missing_end", lambda p: p["window"].pop("end"))
    mut("citation_type_unknown", lambda p: p["citations"].append({"type": "vibes", "ref": "x"}))
    return out


# The evalset criteria (adk eval reads agents/planner/evalsets/test_config.json via
# harness/run_evals.py). EXACT + ignore_args: same tool names, same count, same positions; argument
# content (the batched estimator's drafts, propose_play's play) may differ between runs. With one
# invocation per case the trajectory score is 0 or 1, so 0.8 means "the whole sequence matches".
EVAL_CRITERIA = {
    "criteria": {
        "tool_trajectory_avg_score": {"threshold": 0.8, "match_type": "EXACT", "ignore_args": True},
        "response_match_score": 0.8,
    }
}
TRACE_MARKER = "source=recorded_trace"


def latest_real_traces() -> Path | None:
    """Newest committed eval/raw/planner_traces_*/ recorded against the real model (vertex)."""
    for d in sorted((ROOT / "eval" / "raw").glob("planner_traces_*"), reverse=True):
        summary = d / "summary.json"
        if summary.exists() and json.loads(summary.read_text(encoding="utf-8")).get("backend") == "vertex":
            return d
    return None


def evalset_from_trace(gap_id: str, records: list[dict], summary: dict, trace_rel: str) -> dict:
    """One evalset from one recorded run: the exact user message the model saw, the recorded tool
    names in order (args left empty -- the criterion ignores them), the recorded final text."""
    from harness.record_planner_traces import trace_facts

    user = next(r["content"] for r in records if r.get("kind") == "user")
    facts = trace_facts(records)
    name = f"planner_{gap_id}"
    outcome = "accepted play" if facts["planner_source"] == "model" else f"no accepted model play ({facts['fallback_reason'] or facts['status']})"
    return {
        "eval_set_id": name, "name": name,
        "description": (
            f"{TRACE_MARKER}: planner trajectory for {gap_id} from {trace_rel} "
            f"({summary['backend']} {summary['model']}, prompt {summary['prompt_version']}, recorded {summary['recorded_at']}; "
            f"{len(facts['tool_names'])} tool calls, {facts['revisions']} rejected propose_play, {outcome})"
        ),
        "eval_cases": [{
            "eval_id": f"{name}_case", "conversation": [{
                "invocation_id": f"inv-{gap_id}",
                "user_content": {"parts": [{"text": "".join(p.get("text", "") for p in user.get("parts", []))}], "role": "user"},
                "final_response": {"parts": [{"text": facts["final_text"]}], "role": "model"},
                # tool_responses keeps only each recorded propose_play verdict (valid or not): the
                # trajectory metric reads tool_uses alone, and the stub's replay mode
                # (agents/planner/stub_llm.py) needs the verdicts to reproduce the rejections
                "intermediate_data": {
                    "tool_uses": [{"name": n, "args": {}} for n in facts["tool_names"]],
                    "tool_responses": [{"name": "propose_play", "response": {"valid": v}} for v in facts["propose_play_verdicts"]],
                    "intermediate_responses": [],
                },
            }], "session_input": {"app_name": "taal_planner", "user_id": "planner", "state": {}},
        }],
    }


def build_evalsets_from_traces(trace_dir: Path) -> int:
    trace_dir = trace_dir.resolve()
    summary = json.loads((trace_dir / "summary.json").read_text(encoding="utf-8"))
    es = ROOT / "agents" / "planner" / "evalsets"
    shutil.rmtree(es, ignore_errors=True)
    es.mkdir(parents=True, exist_ok=True)
    rel = str(trace_dir.relative_to(ROOT)) if trace_dir.is_relative_to(ROOT) else str(trace_dir)
    n = 0
    for row in summary["gaps"]:
        gid = row["gap_id"]
        records = [json.loads(line) for line in (trace_dir / f"{gid}.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        if not any(r.get("kind") == "user" for r in records):
            continue  # the run crashed before the model saw anything: nothing to evaluate against
        _write(es / f"{gid}.evalset.json", evalset_from_trace(gid, records, summary, f"{rel}/{gid}.jsonl"))
        n += 1
    _write(es / "test_config.json", EVAL_CRITERIA)
    return n


def evalset_from_events(name: str, gap_id: str, events: list[dict], final_text: str) -> dict:
    tool_uses = [{"name": e["function_call"]["name"], "args": {}} for e in events if e.get("function_call")]
    return {
        "eval_set_id": name, "name": name, "description": f"Planner trajectory for {gap_id} recorded from the stub run",
        "eval_cases": [{
            "eval_id": f"{name}_case", "conversation": [{
                "invocation_id": f"inv-{gap_id}",
                "user_content": {"parts": [{"text": f"Plan gap_id={gap_id} policy_version=v1\nReply DONE <play_id> when propose_play accepts."}], "role": "user"},
                "final_response": {"parts": [{"text": final_text}], "role": "model"},
                "intermediate_data": {"tool_uses": tool_uses, "intermediate_responses": []},
            }], "session_input": {"app_name": "taal_planner", "user_id": "planner", "state": {}},
        }],
    }


async def main_async(data_dir: Path) -> int:
    tenant = load_tenant()
    base = LocalStore(data_dir)
    # clean slate for fixture output
    for d in (FIX / "plays", FIX / "golden_runs", ROOT / "agents" / "planner" / "evalsets"):
        shutil.rmtree(d, ignore_errors=True)
    # 1. plays: demo gaps first, then the largest planner-eligible gaps up to 20
    gaps = base.read("gaps")
    threshold = tenant.thresholds["min_rupees_at_stake_for_planner"]
    order = DEMO_GAPS + [g["gap_id"] for g in gaps if g["gap_id"] not in DEMO_GAPS and g["rupees_at_stake"] >= threshold]
    plays, runs = {}, {}
    for gid in order:
        if len(plays) >= 20:
            break
        out = await run_planner_async(data_dir, gid)
        if out["play"]:
            plays[gid] = out["play"]
            runs[gid] = out
            _write(FIX / "plays" / "valid" / f"{out['play']['play_id']}.json", out["play"])
    for name, p in mutations(plays["gap_chips_ds07"]):
        _write(FIX / "plays" / "invalid" / f"{name}.json", {"mutation": name, "play": p})
    # 2. policy v2 run for the tea gap, in an overlay so the base tenant keeps only the v1 plays
    overlay = OverlayStore(data_dir, ROOT / ".local" / "fixture_overlay")
    overlay.reset()
    for t in ("gaps", "plays", "products", "nodes", "customers", "affinity", "consent", "segments", "estimator_priors", "play_assignments", "inventory_batches", "inbound", "order_lines", "play_outcomes", "sense_runs", "policy"):
        overlay._materialise(t)
    (overlay.root / "manifest.json").write_bytes((data_dir / "manifest.json").read_bytes())
    v2 = await run_planner_async(overlay.root, "gap_tea_ds04", policy_text=POLICY_V2.read_text(encoding="utf-8"), policy_version="v2")
    _write(FIX / "plays" / "valid" / f"{v2['play']['play_id']}.json", v2["play"])
    # 3. golden runs
    gr = FIX / "golden_runs"
    gr.mkdir(parents=True, exist_ok=True)
    for gid in DEMO_GAPS:
        if gid in runs:
            (gr / f"{runs[gid]['run_id']}.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in runs[gid]["events"]), encoding="utf-8")
    (gr / f"{v2['run_id']}.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in v2["events"]), encoding="utf-8")
    # 4. approve + Meena conversation + measure, in the same throwaway overlay
    resp = approve(overlay, tenant, plays["gap_chips_ds07"]["play_id"], FIXED_NOW)
    resp["forecast"]["series"] = resp["forecast"]["series"]
    _write(gr / "approve_chips.json", resp)
    reset_sessions()
    convo = []
    for text in ["Any offers today?", "Do you have Cola Zero?", "add:SKU-MASALA-CHIPS-200G", "STOP"]:
        env = (await run_chat_async(overlay, "CUST-MEENA:web", text, now_iso="2026-09-12T09:05:00Z"))[0]
        convo.append({"user": text, "agent": env})
    _write(gr / "conversation_meena.json", convo)
    for t in ("plays", "play_assignments", "order_lines", "play_outcomes", "estimator_priors", "products"):
        overlay._materialise(t)
    m = run_measure(overlay.root, computed_at="2026-09-19T00:00:00Z")
    _write(gr / "measure_chips.json", {"summary": m, "outcomes": overlay.read("play_outcomes")})
    overlay.reset()
    shutil.rmtree(overlay.root, ignore_errors=True)
    # 5. evalsets: from the committed real-model traces when there are any, else the stub runs
    es = ROOT / "agents" / "planner" / "evalsets"
    es.mkdir(parents=True, exist_ok=True)
    real = latest_real_traces()
    if real is not None:
        n_evalsets = build_evalsets_from_traces(real)
    else:
        n_evalsets = 0
        for gid in ["gap_chips_ds07", "gap_tea_ds04", "gap_cola_ds07", "gap_kaju_ds01", "gap_quinoa_out02"]:
            if gid in runs:
                _write(es / f"{gid}.evalset.json", evalset_from_events(f"planner_{gid}", gid, runs[gid]["events"], f"DONE {runs[gid]['play']['play_id']}"))
                n_evalsets += 1
    # 6. snapshot manifest
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    _write(FIX / "demo_snapshot.json", {
        "generator": {"seed": manifest["seed"], "as_of": manifest["as_of"], "counts": manifest["counts"], "sha256": manifest["sha256"]},
        "sense_run_id": base.read("sense_runs")[-1]["run_id"], "gaps": len(gaps),
        "demo_gaps": {gid: {"play_id": plays[gid]["play_id"], "run_id": runs[gid]["run_id"], "mechanic": plays[gid]["mechanic"], "rupees_at_stake": next(g["rupees_at_stake"] for g in gaps if g["gap_id"] == gid)} for gid in DEMO_GAPS if gid in plays},
        "policy_v2_run": {"gap_id": "gap_tea_ds04", "play_id": v2["play"]["play_id"], "run_id": v2["run_id"], "mechanic": v2["play"]["mechanic"]},
        "approve_chips": {"treated_n": resp["assignment"]["treated_n"], "holdout_n": resp["assignment"]["holdout_n"], "writeoff_before_inr": resp["forecast"]["writeoff_before_inr"], "writeoff_after_inr": resp["forecast"]["writeoff_after_inr"]},
        "note": "Rebuilt by `python -m harness.build_fixtures` after `make generate`; all values derive from the seeded tenant.",
    })
    print(f"fixtures: {len(plays) + 1} valid plays, {len(mutations(plays['gap_chips_ds07']))} invalid, {len(DEMO_GAPS) + 1} golden runs, {n_evalsets} evalsets")
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse
    import os

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--evalsets-from-traces", default=None, help="rebuild only agents/planner/evalsets/ from this recorded trace dir")
    args = ap.parse_args(argv)
    if args.evalsets_from_traces:
        n = build_evalsets_from_traces(Path(args.evalsets_from_traces))
        print(f"fixtures: {n} evalsets from {args.evalsets_from_traces}")
        return 0
    n = _write_garment_swatches()
    print(f"fixtures: {n} stylist photo swatches")
    return asyncio.run(main_async(Path(os.environ.get("TAAL_DATA_DIR", ".local/data")).resolve()))


if __name__ == "__main__":
    sys.exit(main())
