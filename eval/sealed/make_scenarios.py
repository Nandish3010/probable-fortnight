"""Regenerate eval/sealed/scenarios.json, baselines.json and cell_report.json deterministically (no model).

    python -m eval.sealed.make_scenarios --seeds 40617833 [--data-root .local/sealed] [--out eval/sealed]

Scenarios are stratified by FEATURES of the gap, never by the oracle's answer. Steps: generate the seed's tenant into
a gitignored dir (`data.generator`), run Sense (`jobs.sense`) as the product does, take the pool, assign cells, pick
2 gaps per cell, then run the oracle (eval/sealed/oracle.py) on the 36 chosen gaps for the baselines file.

Pool: gap type in {online_sellby_breach, expiry_writeoff}, rupees_at_stake >= the tenant's planner threshold (500),
lot 10 to 500 units, deadline 3 to 40 days after the tenant's as-of date, not one of the generator's planted demo
gaps (manifest "planted").

Cells (18): gap type (2) x lot band (10-60 / 61-200 / 201-500 units) x deadline band (3-10 / 11-21 / 22-40 days).
Selection rule: inside a cell sort gaps by sha256("sealed-v2|" + seed + "|" + gap_id) and take the first 2.
Borrowing rule, if a cell holds fewer than 2: take the missing gaps from the nearest cell of the SAME gap type, by
Manhattan distance over (lot band, deadline band) indices, ties broken by the lower (lot band, deadline band) pair,
using that cell's next gaps in the same hash order; every borrowed scenario records `borrowed_from`. If the same-type
cells together cannot supply the 2, the script stops (exit 2) and writes nothing but cell_report.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CLEARING_TYPES = ("online_sellby_breach", "expiry_writeoff")
LOT_BANDS = ((10, 60), (61, 200), (201, 500))
DAY_BANDS = ((3, 10), (11, 21), (22, 40))
PER_CELL = 2
SALT = "sealed-v2"


def tenant_dir(data_root: Path, seed: int) -> Path:
    return data_root / f"seed_{seed}"


def ensure_tenant(data_root: str | Path, seed: int) -> Path:
    """Generate and Sense one seed's tenant if its data dir is missing (deterministic: same seed, same bytes)."""
    d = tenant_dir(Path(data_root), seed)
    if (d / "gaps.jsonl").exists() and (d / "manifest.json").exists():
        return d
    env = {**os.environ, "TAAL_MODEL_BACKEND": "stub"}
    subprocess.run([sys.executable, "-m", "data.generator", "--out", str(d), "--seed", str(seed), "--quiet"], check=True, cwd=ROOT, env=env)
    subprocess.run([sys.executable, "-m", "jobs.sense", "--data", str(d)], check=True, cwd=ROOT, env=env, stdout=subprocess.DEVNULL)
    return d


def _band(v: float, bands: tuple[tuple[int, int], ...]) -> int | None:
    for i, (lo, hi) in enumerate(bands):
        if lo <= v <= hi:
            return i
    return None


def pool_for_seed(data_dir: Path, seed: int) -> list[dict[str, Any]]:
    from agents.gate.config import load_tenant
    from agents.gate.store import LocalStore

    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    as_of = date.fromisoformat(manifest["as_of"])
    planted = set((manifest.get("planted") or {}).keys())
    threshold = float(load_tenant().thresholds["min_rupees_at_stake_for_planner"])
    out = []
    for g in LocalStore(data_dir).read("gaps"):
        if g["type"] not in CLEARING_TYPES or g["gap_id"] in planted or float(g["rupees_at_stake"]) < threshold:
            continue
        days = (date.fromisoformat(g["deadline_date"]) - as_of).days
        lb, db = _band(g["units_at_risk"], LOT_BANDS), _band(days, DAY_BANDS)
        if lb is None or db is None:
            continue
        out.append({**g, "seed": seed, "days_to_deadline": days, "lot_band": lb, "day_band": db})
    return out


def _hkey(r: dict[str, Any]) -> str:
    return hashlib.sha256(f"{SALT}|{r['seed']}|{r['gap_id']}".encode()).hexdigest()


def choose(pool: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cells: dict[tuple[str, int, int], list[dict[str, Any]]] = {}
    for t in CLEARING_TYPES:
        for i in range(len(LOT_BANDS)):
            for j in range(len(DAY_BANDS)):
                cells[(t, i, j)] = []
    for r in pool:
        cells[(r["type"], r["lot_band"], r["day_band"])].append(r)
    for lst in cells.values():
        lst.sort(key=_hkey)
    counts = {f"{t}|lot{i}|days{j}": len(v) for (t, i, j), v in cells.items()}
    nxt = {k: 0 for k in cells}
    chosen: list[dict[str, Any]] = []
    borrowed: list[dict[str, Any]] = []
    for key in sorted(cells):
        t, i, j = key
        for _ in range(PER_CELL):
            src = key
            if nxt[key] >= len(cells[key]):
                cands = sorted((k for k in cells if k[0] == t and k != key and nxt[k] < len(cells[k])), key=lambda k: (abs(k[1] - i) + abs(k[2] - j), k[1], k[2]))
                if not cands:
                    raise SystemExit(f"cell {key} cannot be filled: no same-type cell has spare gaps")
                src = cands[0]
            r = dict(cells[src][nxt[src]])
            nxt[src] += 1
            r["cell"] = {"gap_type": t, "lot_band": i, "day_band": j}
            if src != key:
                r["borrowed_from"] = {"gap_type": src[0], "lot_band": src[1], "day_band": src[2]}
                borrowed.append({"cell": list(key), "from": list(src), "gap_id": r["gap_id"]})
            chosen.append(r)
    return chosen, {"pool_size": len(pool), "cell_counts": counts, "borrowed": borrowed}


def compact(entry: dict[str, Any]) -> dict[str, Any]:
    keep = ("class", "mechanic", "mechanic_params", "segments", "holdout_fraction", "audience_after_consent", "recovery_inr")
    return {k: entry[k] for k in keep if k in entry}


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def build(seeds: list[int], data_root: Path, out: Path) -> dict[str, Any]:
    from eval.sealed import oracle

    scenarios, baselines, report = [], {}, {"seeds": seeds, "per_cell": PER_CELL, "by_seed": {}}
    n = 0
    for seed in seeds:
        d = ensure_tenant(data_root, seed)
        pool = pool_for_seed(d, seed)
        chosen, info = choose(pool)
        report["by_seed"][str(seed)] = info
        solved = oracle.solve_gaps(d, [r["gap_id"] for r in chosen])
        for r in chosen:
            n += 1
            sid = f"S{n:02d}"
            o = solved[r["gap_id"]]
            ev = r["evidence"]
            list_price = ev["unit_cost"] + ev["margin_per_unit"]
            gap_fields = {k: r[k] for k in ("gap_id", "type", "sku", "node_id", "batch_id", "units_at_risk", "deadline_date", "deadline_type", "rupees_at_stake", "days_to_deadline")}
            consented = max(p.get("audience_after_consent", 0) for p in o["per_class_best"].values())
            sc = {"scenario_id": sid, "seed": seed, "data_dir": f"seed_{seed}", "cell": r["cell"], "gap": gap_fields,
                  "features": {"unit_cost": ev["unit_cost"], "list_price": round(list_price, 2), "margin_per_unit": ev["margin_per_unit"], "margin_pct_of_price": round(ev["margin_per_unit"] / list_price * 100, 1), "category": ev.get("category"), "consented_audience": consented}}
            if "borrowed_from" in r:
                sc["borrowed_from"] = r["borrowed_from"]
            scenarios.append(sc)
            baselines[sid] = {"gap_id": r["gap_id"], "seed": seed, "do_nothing_recovery_inr": 0.0, "blanket20_recovery_inr": o["blanket20_recovery_inr"],
                              "oracle_upper_bound_inr": o["best"]["recovery_inr"], "best_classes_tied": o["best_classes_tied"],
                              "oracle_top3": [compact(p) for p in o["top3"]], "grid_sizes": o["grid_sizes"]}
    out.mkdir(parents=True, exist_ok=True)
    doc = {"schema_version": 2, "seeds": seeds, "cells": "gap type (2) x lot band (3) x deadline band (3), 2 per cell", "lot_bands_units": LOT_BANDS, "deadline_bands_days": DAY_BANDS,
           "model_calls": 0, "reproduce": [f"python -m data.generator --out .local/sealed/seed_{s} --seed {s}; python -m jobs.sense --data .local/sealed/seed_{s}" for s in seeds], "scenarios": scenarios}
    sp, bp = out / "scenarios.json", out / "baselines.json"
    sp.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    bp.write_text(json.dumps({"schema_version": 2, "note": "oracle_upper_bound_inr is an estimator upper bound, not a best play (see PROTOCOL.md section 7)", "baselines": baselines}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "cell_report.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    return {"scenarios.json": sha256_file(sp), "baselines.json": sha256_file(bp), "cell_report.json": sha256_file(out / "cell_report.json")}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", required=True)
    ap.add_argument("--data-root", default=str(ROOT / ".local" / "sealed"))
    ap.add_argument("--out", default=str(ROOT / "eval" / "sealed"))
    args = ap.parse_args(argv)
    os.environ.setdefault("TAAL_MODEL_BACKEND", "stub")
    seeds = [int(s) for s in args.seeds.split(",")]
    if 20260912 in seeds:
        print("seed 20260912 is the demo tenant's")
        return 1
    data_root = Path(args.data_root)
    data_root.mkdir(parents=True, exist_ok=True)
    print(json.dumps(build(seeds, data_root, Path(args.out)), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
