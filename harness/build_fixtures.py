"""Rebuild the committed fixtures from the generated tenant (deterministic; run after `make generate`).

    python -m harness.build_fixtures

Writes: fixtures/plays/valid/*.json (20 golden plays from the stub planner), fixtures/plays/invalid/*.json
(20 mutations, each with the mutation named), fixtures/golden_runs/*.jsonl (planner traces for the demo
gaps under policy v1 and v2, the chips approve response, Meena's conversation), agents/planner/evalsets/*.evalset.json
(ADK evalset format, tool trajectories from the recorded runs), fixtures/demo_snapshot.json.
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
    # 5. evalsets
    es = ROOT / "agents" / "planner" / "evalsets"
    es.mkdir(parents=True, exist_ok=True)
    for gid in ["gap_chips_ds07", "gap_tea_ds04", "gap_cola_ds07", "gap_kaju_ds01", "gap_quinoa_out02"]:
        if gid in runs:
            _write(es / f"{gid}.evalset.json", evalset_from_events(f"planner_{gid}", gid, runs[gid]["events"], f"DONE {runs[gid]['play']['play_id']}"))
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
    print(f"fixtures: {len(plays) + 1} valid plays, {len(mutations(plays['gap_chips_ds07']))} invalid, {len(DEMO_GAPS) + 1} golden runs, 5 evalsets")
    return 0


def main() -> int:
    import os

    return asyncio.run(main_async(Path(os.environ.get("TAAL_DATA_DIR", ".local/data")).resolve()))


if __name__ == "__main__":
    sys.exit(main())
