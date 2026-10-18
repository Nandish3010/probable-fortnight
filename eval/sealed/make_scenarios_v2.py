"""Regenerate eval/sealed/v2/scenarios.json and baselines.json deterministically (no model call).

    python -m eval.sealed.make_scenarios_v2 --seed 71903482 [--data-root .local/sealed] [--out eval/sealed/v2]

Sealed eval v2 (protocol: eval/sealed/PROTOCOL_v2.md). 36 scenarios from ONE new seed, two strata:

MARKDOWN stratum: the gaps where the best baseline is a markdown, by a FIXED RULE read from the baselines, not
chosen by hand. Per pool gap, with no model:
  md_best   = highest recovery among the `markdown` plays at the tenant depths (10 / 20 / 35%) whose net margin clears
              the category margin floor (est-v2, the same demand model as every play); the lot must be online (not
              at an outlet) and not past its online sell-by;
  ref_best  = highest recovery among the oracle's legal non-markdown plays (coupon, bundle, outlet_markdown,
              transfer_plus_nudge) with the beats_markdown gate OFF (eval/sealed/oracle.py);
  markdown_is_best_baseline  <=>  md_best >= INR 500  and  md_best > ref_best.
EVERY pool gap that satisfies the rule is in the stratum (at most 18; the pool of this seed yields fewer, which is a
finding: a markdown is rarely the best play once the margin floor and the demand model apply).

FEATURE stratum: the remaining 36 - (stratum size) scenarios by v1's rule: pool = gap type in {online_sellby_breach,
expiry_writeoff}, rupees_at_stake >= 500, lot 10-500 units, deadline 3-40 days after the as-of date, not a planted demo
gap (`make_scenarios.pool_for_seed`), not in the markdown stratum. 18 cells = gap type x lot band (10-60 / 61-200 /
201-500) x deadline band (3-10 / 11-21 / 22-40 days). Quota per cell: 2 in the first cells in sorted cell-key order
until the stratum is filled, 1 in the rest (so every cell is used). Inside a cell sort by
sha256("sealed-v2|<seed>|<gap_id>"); a cell with too few gaps borrows from the nearest cell of the same gap type
(Manhattan distance, ties to the lower pair) and records `borrowed_from`.

`markdown_is_best_baseline` is computed for ALL 36 scenarios (a feature-stratum gap can satisfy it too); the metric
"chooses a markdown where the best baseline is a markdown: n of N" counts N = every scenario with the flag.

Baselines per scenario: do nothing = 0; blanket markdown at 10/20/35% under v1's definition (do_nothing_inr -
blanket_markdown_inr, the product's counterfactual; blanket20 is the primary baseline, as in v1); the best allowed
markdown PLAY (depth, recovery); the best non-markdown reference; `oracle_upper_bound_inr` = max of the two (an
estimator upper bound over every lever, not a best play).
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from eval.sealed import make_scenarios as v1

ROOT = Path(__file__).resolve().parents[2]
SALT_F = "sealed-v2"
SALT_M = "sealed-v2b"
MD_MIN_INR = 500.0
MD_COUNT = 18
TOTAL = 36
DEPTHS = (10.0, 20.0, 35.0)


def _hash(salt: str, r: dict[str, Any]) -> str:
    return hashlib.sha256(f"{salt}|{r['seed']}|{r['gap_id']}".encode()).hexdigest()


def choose_feature(pool: list[dict[str, Any]], count: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """`count` gaps by v1's rule (hash order inside a cell, nearest same-type cell when empty): quota 2 per cell in cell-key order until `count` is reachable with 1 in the rest."""
    cells: dict[tuple[str, int, int], list[dict[str, Any]]] = {(t, i, j): [] for t in v1.CLEARING_TYPES for i in range(len(v1.LOT_BANDS)) for j in range(len(v1.DAY_BANDS))}
    for r in pool:
        cells[(r["type"], r["lot_band"], r["day_band"])].append(r)
    for lst in cells.values():
        lst.sort(key=lambda r: _hash(SALT_F, r))
    nxt = {k: 0 for k in cells}
    chosen, borrowed = [], []
    keys = sorted(cells)
    extra = max(0, count - len(keys))  # cells that get a second gap
    for pos, key in enumerate(keys):
        t, i, j = key
        for _ in range(2 if pos < extra else 1):
            src = key
            if nxt[key] >= len(cells[key]):
                cands = sorted((k for k in cells if k[0] == t and k != key and nxt[k] < len(cells[k])), key=lambda k: (abs(k[1] - i) + abs(k[2] - j), k[1], k[2]))
                if not cands:
                    raise SystemExit(f"cell {key} cannot be filled")
                src = cands[0]
            r = dict(cells[src][nxt[src]])
            nxt[src] += 1
            r["cell"] = {"gap_type": t, "lot_band": i, "day_band": j}
            if src != key:
                r["borrowed_from"] = {"gap_type": src[0], "lot_band": src[1], "day_band": src[2]}
                borrowed.append({"cell": list(key), "from": list(src), "gap_id": r["gap_id"]})
            chosen.append(r)
    return chosen, {"pool_size": len(pool), "cell_counts": {f"{t}|lot{i}|days{j}": len(v) for (t, i, j), v in cells.items()}, "borrowed": borrowed}


def markdown_table(ctx: Any, gap_id: str) -> dict[str, Any]:
    """Markdown baselines for one gap under est-v2 with no model: blanket (counterfactual) and play recovery per depth."""
    from agents.gate import guardrails as gr
    from agents.gate.estimator import estimate, recovery_of
    from agents.planner import tools as pt

    gap = pt._gap(ctx, gap_id)
    blocked = pt._markdown_blocked(ctx, gap)
    out: dict[str, Any] = {"markdown_blocked": blocked, "depths": {}}
    for pct in DEPTHS:
        draft = {"gap_id": gap_id, "objective": "clear_online_sellby", "mechanic": "markdown", "mechanic_params": {"markdown_pct": pct},
                 "target": {"sku": gap["sku"], "node_ids": [gap["node_id"]], "batch_ids": [], "units": int(gap["units_at_risk"]), "deadline_date": gap["deadline_date"], "deadline_type": gap["deadline_type"]},
                 "holdout": {"fraction": 0.1, "seed": "seed-baseline", "min_treated_n": 20}}
        pt.apply_derived_audience(ctx, draft)
        est = estimate(draft, pt._estimator_context(ctx, draft))
        floor_ok = bool(gr.RULES["margin_floor"](draft, pt._guardrail_context(ctx, draft))["passed"])
        cf = est["counterfactuals"]
        out["depths"][f"{pct:g}"] = {"blanket_recovery_inr": round(cf["do_nothing_inr"] - cf["blanket_markdown_inr"], 2), "markdown_play_recovery_inr": recovery_of(est), "clears_margin_floor": floor_ok,
                                     "units": est["expected_outcome"]["units"]}
    allowed = [(k, v) for k, v in out["depths"].items() if v["clears_margin_floor"] and not blocked]
    best = max(allowed, key=lambda kv: (round(kv[1]["markdown_play_recovery_inr"], 2), -float(kv[0])), default=None)
    out["best_markdown_play_pct"] = float(best[0]) if best else None
    out["best_markdown_play_recovery_inr"] = best[1]["markdown_play_recovery_inr"] if best else 0.0
    return out


def reference_without_markdown(data_dir: Path, gap_id: str, ctx: Any) -> dict[str, Any]:
    """Oracle's best legal non-markdown play with the beats_markdown gate off (the gate would reject the very plays
    being measured against the markdown)."""
    from eval.sealed import oracle

    gate_off = dataclasses.replace(ctx, tenant=dataclasses.replace(ctx.tenant, raw={**ctx.tenant.raw, "markdown": {**ctx.tenant.raw.get("markdown", {}), "beats_markdown": False}}))
    sol = oracle.solve_gap(data_dir, gap_id, gate_off)
    ranked = [p for c, p in sol["per_class_best"].items() if c not in ("blanket_markdown", "do_nothing")]
    best = max(ranked, key=lambda p: p["recovery_inr"], default=None)
    return {"ref_best_inr": best["recovery_inr"] if best else 0.0, "ref_best_class": best["class"] if best else None, "consented_audience": max((p.get("audience_after_consent", 0) for p in sol["per_class_best"].values()), default=0)}


def build(seed: int, data_root: Path, out: Path) -> dict[str, Any]:
    from agents.planner.context import reset_context, set_context
    from eval.sealed import oracle

    d = v1.ensure_tenant(data_root, seed)
    pool = v1.pool_for_seed(d, seed)
    ctx = oracle.cached_context(d, "v2_baselines")
    token = set_context(ctx)
    try:
        tables: dict[str, dict[str, Any]] = {}

        def table(gid: str) -> dict[str, Any]:
            if gid not in tables:
                tables[gid] = markdown_table(ctx, gid)
            return tables[gid]

        refs: dict[str, dict[str, Any]] = {}
        md_chosen: list[dict[str, Any]] = []
        for r in sorted(pool, key=lambda r: _hash(SALT_M, r)):
            if table(r["gap_id"])["best_markdown_play_recovery_inr"] < MD_MIN_INR:
                continue
            refs[r["gap_id"]] = reference_without_markdown(d, r["gap_id"], ctx)
            if table(r["gap_id"])["best_markdown_play_recovery_inr"] > refs[r["gap_id"]]["ref_best_inr"] and len(md_chosen) < MD_COUNT:
                md_chosen.append({**r, "cell": {"gap_type": r["type"], "lot_band": r["lot_band"], "day_band": r["day_band"]}})
        md_ids = {r["gap_id"] for r in md_chosen}
        feat, info = choose_feature([r for r in pool if r["gap_id"] not in md_ids], TOTAL - len(md_chosen))
        info["markdown_stratum"] = {"pool_gaps_with_md_best_ge_500": len(refs), "chosen": len(md_chosen)}
        chosen = [dict(r, stratum="feature") for r in feat] + [dict(r, stratum="markdown_best") for r in md_chosen]
        scenarios, baselines = [], {}
        for n, r in enumerate(chosen, start=1):
            sid = f"S{n:02d}"
            gid = r["gap_id"]
            t = table(gid)
            ref = refs.get(gid) or reference_without_markdown(d, gid, ctx)
            ev = r["evidence"]
            list_price = ev["unit_cost"] + ev["margin_per_unit"]
            gap_fields = {k: r[k] for k in ("gap_id", "type", "sku", "node_id", "batch_id", "units_at_risk", "deadline_date", "deadline_type", "rupees_at_stake", "days_to_deadline")}
            sc = {"scenario_id": sid, "seed": seed, "data_dir": f"seed_{seed}", "stratum": r["stratum"], "cell": r["cell"],
                  "gap": gap_fields, "features": {"unit_cost": ev["unit_cost"], "list_price": round(list_price, 2), "margin_per_unit": ev["margin_per_unit"], "margin_pct_of_price": round(ev["margin_per_unit"] / list_price * 100, 1), "category": ev.get("category"), "consented_audience": ref["consented_audience"]}}
            if "borrowed_from" in r:
                sc["borrowed_from"] = r["borrowed_from"]
            scenarios.append(sc)
            blankets = {k: v["blanket_recovery_inr"] for k, v in t["depths"].items()}
            md_best, ref_best = t["best_markdown_play_recovery_inr"], ref["ref_best_inr"]
            baselines[sid] = {
                "gap_id": gid, "seed": seed, "stratum": r["stratum"], "do_nothing_recovery_inr": 0.0,
                "blanket20_recovery_inr": blankets["20"], "blanket10_recovery_inr": blankets["10"], "blanket35_recovery_inr": blankets["35"], "best_blanket_recovery_inr": max(blankets.values()),
                "markdown_plays": t["depths"], "best_markdown_play_pct": t["best_markdown_play_pct"], "best_markdown_play_recovery_inr": md_best,
                "best_nonmarkdown_reference_inr": ref_best, "best_nonmarkdown_reference_class": ref["ref_best_class"],
                "markdown_is_best_baseline": bool(md_best >= MD_MIN_INR and md_best > ref_best),
                "oracle_upper_bound_inr": max(md_best, ref_best),
            }
    finally:
        reset_context(token)
    out.mkdir(parents=True, exist_ok=True)
    doc = {"schema_version": 3, "seeds": [seed], "strata": {"feature": "first scenarios: v1's cell rule (see make_scenarios_v2 docstring)", "markdown_best": "last scenarios: every pool gap with markdown_is_best_baseline (fixed rule)"},
           "lot_bands_units": v1.LOT_BANDS, "deadline_bands_days": v1.DAY_BANDS, "model_calls": 0,
           "reproduce": [f"python -m data.generator --out .local/sealed/seed_{seed} --seed {seed}; python -m jobs.sense --data .local/sealed/seed_{seed}; python -m eval.sealed.make_scenarios_v2 --seed {seed}"], "scenarios": scenarios}
    sp, bp, cp = out / "scenarios.json", out / "baselines.json", out / "cell_report.json"
    sp.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    bp.write_text(json.dumps({"schema_version": 3, "note": "blanket* = do_nothing_inr - blanket_markdown_inr (v1's definition); markdown_plays = the `markdown` mechanic's own recovery per depth; oracle_upper_bound_inr is an estimator upper bound, not a best play", "baselines": baselines}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    cp.write_text(json.dumps({"seed": seed, **info}, indent=1) + "\n", encoding="utf-8")
    return {"scenarios.json": v1.sha256_file(sp), "baselines.json": v1.sha256_file(bp), "cell_report.json": v1.sha256_file(cp),
            "markdown_is_best_baseline_n": sum(b["markdown_is_best_baseline"] for b in baselines.values()), "by_stratum": {s: sum(1 for b in baselines.values() if b["stratum"] == s and b["markdown_is_best_baseline"]) for s in ("feature", "markdown_best")}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", required=True, type=int)
    ap.add_argument("--data-root", default=str(ROOT / ".local" / "sealed"))
    ap.add_argument("--out", default=str(ROOT / "eval" / "sealed" / "v2"))
    args = ap.parse_args(argv)
    os.environ.setdefault("TAAL_MODEL_BACKEND", "stub")
    if args.seed in (20260912, 40617833):
        print("seed is the demo tenant's or sealed v1's")
        return 1
    Path(args.data_root).mkdir(parents=True, exist_ok=True)
    print(json.dumps(build(args.seed, Path(args.data_root), Path(args.out)), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
