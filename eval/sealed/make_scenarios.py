"""Regenerate eval/sealed/scenarios.json and oracle_answers.json deterministically (no model).

    python -m eval.sealed.make_scenarios --seeds 40617833 [--data-root .local/sealed] [--out eval/sealed]

Steps: generate each seed's tenant into a gitignored dir (`data.generator`), run Sense (`jobs.sense`) as the
product does, run the oracle (eval/sealed/oracle.py) on every planner-eligible clearing gap (online_sellby_breach
and expiry_writeoff; the lots a play can clear), assign each gap a stratum from the ORACLE's answer, and select 6
per stratum by the fixed rule below. If any stratum cannot reach 6 the script writes `strata_report.json`, prints
the counts and exits with status 2 WITHOUT writing scenarios: definitions are not bent to fill a stratum.

Strata (from the oracle's best class; "clear" = best beats the runner-up class by at least 10%):
  transfer, targeted_offer (coupon or outlet markdown, which the estimator scores identically), bundle,
  blanket_markdown, do_nothing: that class is best and clear. close_call: best beats the runner-up by under 10%
  (any classes). do_nothing means no legal play recovers more than 0.

Pool: planner-eligible (rupees_at_stake >= tenant threshold), clearing gap types, lot 10 to 500 units, sell-by
distance 3 to 40 days from the tenant's as-of date, and not one of the generator's planted demo gaps.

Selection rule (no hand-picking). Within a stratum, each gap falls in one of 9 cells: lot size
(10-49 / 50-149 / 150-500 units) x sell-by distance (3-13 / 14-26 / 27-40 days). Gaps in a cell are ordered by
sha256("sealed-v1|" + seed + "|" + gap_id). Cells are visited round-robin in the fixed order (small lot, near)
to (large lot, far), taking the next gap of each non-empty cell, until 6 are chosen. Margin level and consented
audience size are not selection keys; the spread achieved is reported in `strata_report.json`.
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
STRATA = ("transfer", "targeted_offer", "bundle", "blanket_markdown", "do_nothing", "close_call")
PER_STRATUM = 6
CLEAR_MARGIN = 0.10
CLEARING_TYPES = ("online_sellby_breach", "expiry_writeoff")
LOT_BINS = ((10, 49), (50, 149), (150, 500))
DAY_BINS = ((3, 13), (14, 26), (27, 40))
CLASS_STRATUM = {"transfer_plus_nudge": "transfer", "coupon": "targeted_offer", "outlet_markdown": "targeted_offer", "bundle": "bundle", "blanket_markdown": "blanket_markdown", "do_nothing": "do_nothing"}
SALT = "sealed-v1"


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


def _bin(v: float, bins: tuple[tuple[int, int], ...]) -> int | None:
    for i, (lo, hi) in enumerate(bins):
        if lo <= v <= hi:
            return i
    return None


def stratum_of(res: dict[str, Any]) -> str:
    best = res["best"]
    gap = res["gap_to_runner_up"]
    if best["class"] == "do_nothing":
        return "do_nothing"
    if gap is not None and gap < CLEAR_MARGIN:
        return "close_call"
    return CLASS_STRATUM[best["class"]]


def pool_for_seed(data_dir: Path, as_of: date, planted: set[str]) -> list[dict[str, Any]]:
    from agents.gate.store import LocalStore

    out = []
    for g in LocalStore(data_dir).read("gaps"):
        if g["type"] not in CLEARING_TYPES or g["gap_id"] in planted:
            continue
        days = (date.fromisoformat(g["deadline_date"]) - as_of).days
        if _bin(g["units_at_risk"], LOT_BINS) is None or _bin(days, DAY_BINS) is None:
            continue
        out.append({**g, "days_to_deadline": days})
    return out


def compact(entry: dict[str, Any]) -> dict[str, Any]:
    keep = ("class", "mechanic", "mechanic_params", "segments", "holdout_fraction", "audience_after_consent", "recovery_inr")
    return {k: entry[k] for k in keep if k in entry}


def build(seeds: list[int], data_root: Path, solve_cache: Path | None = None) -> dict[str, Any]:
    from eval.sealed import oracle

    pools: dict[str, list[dict[str, Any]]] = {s: [] for s in STRATA}
    for seed in seeds:
        d = ensure_tenant(data_root, seed)
        manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        as_of = date.fromisoformat(manifest["as_of"])
        planted = set((manifest.get("planted") or {}).keys())
        rows = pool_for_seed(d, as_of, planted)
        cache = (solve_cache or data_root) / f"oracle_pool_{seed}.json"
        solved: dict[str, Any] = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
        todo = [r["gap_id"] for r in rows if r["gap_id"] not in solved]
        if todo:
            solved.update(oracle.solve_gaps(d, todo))
            cache.write_text(json.dumps(solved, default=str), encoding="utf-8")
        from agents.gate.config import load_tenant

        threshold = float(load_tenant().thresholds["min_rupees_at_stake_for_planner"])
        for r in rows:
            res = solved[r["gap_id"]]
            if r["rupees_at_stake"] < threshold:
                continue
            pools[stratum_of(res)].append({**r, "seed": seed, "oracle": res})
    counts_pool = {s: len(v) for s, v in pools.items()}
    chosen = {s: select_multi(v) for s, v in pools.items()}
    return {"pools": counts_pool, "chosen": chosen}


def select_multi(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Selection over rows from one or several seeds: the per-seed hash key keeps the order deterministic."""
    cells: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for r in rows:
        cells.setdefault((_bin(r["units_at_risk"], LOT_BINS), _bin(r["days_to_deadline"], DAY_BINS)), []).append(r)  # type: ignore[arg-type]
    for lst in cells.values():
        lst.sort(key=lambda r: hashlib.sha256(f"{SALT}|{r['seed']}|{r['gap_id']}".encode()).hexdigest())
    order = [(i, j) for i in range(len(LOT_BINS)) for j in range(len(DAY_BINS))]
    chosen: list[dict[str, Any]] = []
    while len(chosen) < PER_STRATUM and any(cells.get(c) for c in order):
        for c in order:
            if cells.get(c) and len(chosen) < PER_STRATUM:
                chosen.append(cells[c].pop(0))
    return chosen


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write_files(seeds: list[int], built: dict[str, Any], out: Path, provisional: bool = False) -> dict[str, str]:
    scenarios, answers = [], {}
    n = 0
    for stratum in STRATA:
        for r in built["chosen"][stratum]:
            n += 1
            sid = f"S{n:02d}"
            o = r["oracle"]
            gap_fields = {k: r[k] for k in ("gap_id", "type", "sku", "node_id", "batch_id", "units_at_risk", "deadline_date", "deadline_type", "rupees_at_stake", "days_to_deadline")}
            gap_fields["unit_cost"] = r["evidence"].get("unit_cost")
            gap_fields["margin_per_unit"] = r["evidence"].get("margin_per_unit")
            gap_fields["category"] = r["evidence"].get("category")
            scenarios.append({"scenario_id": sid, "stratum": stratum, "seed": r["seed"], "data_dir": f"seed_{r['seed']}", "gap": gap_fields,
                              "oracle_best_class": o["best"]["class"], "oracle_gap_to_runner_up": o["gap_to_runner_up"], "consented_audience_best": o["best"].get("audience_after_consent")})
            answers[sid] = {"gap_id": r["gap_id"], "seed": r["seed"], "top3": [compact(p) for p in o["top3"]], "best_classes_tied": o["best_classes_tied"],
                            "best_recovery_inr": o["best"]["recovery_inr"], "blanket20_recovery_inr": o["blanket20_recovery_inr"], "do_nothing_recovery_inr": 0.0,
                            "grid_sizes": o["grid_sizes"]}
    doc = {"schema_version": 1, "provisional": provisional, "seeds": seeds, "per_stratum": PER_STRATUM, "model_calls": 0,
           "reproduce": [f"python -m data.generator --out .local/sealed/seed_{s} --seed {s}; python -m jobs.sense --data .local/sealed/seed_{s}" for s in seeds],
           "scenarios": scenarios}
    out.mkdir(parents=True, exist_ok=True)
    sp, ap = out / "scenarios.json", out / "oracle_answers.json"
    sp.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    ap.write_text(json.dumps({"schema_version": 1, "oracle": "eval/sealed/oracle.py", "answers": answers}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"scenarios.json": sha256_file(sp), "oracle_answers.json": sha256_file(ap)}


def spread(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    f = lambda xs: [min(xs), max(xs)]  # noqa: E731
    return {"units_at_risk": f([r["units_at_risk"] for r in rows]), "days_to_deadline": f([r["days_to_deadline"] for r in rows]),
            "margin_per_unit": f([r["evidence"].get("margin_per_unit") for r in rows]), "consented_audience": f([r["oracle"]["best"].get("audience_after_consent", 0) for r in rows])}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", required=True, help="comma-separated generator seeds")
    ap.add_argument("--data-root", default=str(ROOT / ".local" / "sealed"))
    ap.add_argument("--out", default=str(ROOT / "eval" / "sealed"))
    ap.add_argument("--provisional", default=None, help="DRY-RUN ONLY: if a stratum is short, fill the 36 from the other strata (largest pool first) and write to --out; marked provisional")
    args = ap.parse_args(argv)
    os.environ.setdefault("TAAL_MODEL_BACKEND", "stub")
    seeds = [int(s) for s in args.seeds.split(",")]
    if 20260912 in seeds:
        print("seed 20260912 is the demo tenant's")
        return 1
    data_root = Path(args.data_root)
    data_root.mkdir(parents=True, exist_ok=True)
    built = build(seeds, data_root)
    out = Path(args.out)
    report = {"seeds": seeds, "pool_counts": built["pools"], "chosen_counts": {s: len(v) for s, v in built["chosen"].items()},
              "spread": {s: spread(v) for s, v in built["chosen"].items()}, "per_stratum_target": PER_STRATUM}
    short = [s for s in STRATA if len(built["chosen"][s]) < PER_STRATUM]
    report["short_strata"] = short
    if short and not args.provisional:
        out.mkdir(parents=True, exist_ok=True)
        (out / "strata_report.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=1))
        print(f"STOP: strata {short} cannot reach {PER_STRATUM}; no scenario files written")
        return 2
    if short:
        used = {r["gap_id"] for v in built["chosen"].values() for r in v}
        # fill from any unused pool gap, in a fixed hash order
        pool_rows = _rebuild_rows(seeds, data_root)
        for s in short:
            need = PER_STRATUM - len(built["chosen"][s])
            extra = [r for r in sorted(pool_rows, key=lambda r: hashlib.sha256(f"fill|{r['seed']}|{r['gap_id']}".encode()).hexdigest()) if r["gap_id"] not in used]
            for r in extra[:need]:
                built["chosen"][s].append(r)
                used.add(r["gap_id"])
    hashes = write_files(seeds, built, Path(args.provisional or out), provisional=bool(args.provisional))
    (Path(args.provisional or out) / "strata_report.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"counts": report["chosen_counts"], "sha256": hashes}, indent=1))
    return 0


def _rebuild_rows(seeds: list[int], data_root: Path) -> list[dict[str, Any]]:
    rows = []
    for seed in seeds:
        d = tenant_dir(data_root, seed)
        manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        solved = json.loads((data_root / f"oracle_pool_{seed}.json").read_text(encoding="utf-8"))
        for r in pool_for_seed(d, date.fromisoformat(manifest["as_of"]), set((manifest.get("planted") or {}).keys())):
            if r["gap_id"] in solved and solved[r["gap_id"]]["planner_eligible"]:
                rows.append({**r, "seed": seed, "oracle": solved[r["gap_id"]]})
    return rows


if __name__ == "__main__":
    sys.exit(main())
