"""Pick the planner evalset gaps from the seeded tenant: 50 gaps, stratified by gap type x node kind.

    python -m harness.select_eval_gaps [--n 50] [--out eval/raw/planner_evalset_selection_<date>.json]

The rule (also written into the output so the selection can be checked against it):

1. Only planner-eligible gaps (agents/planner/governor.planner_eligible: rupees at stake >= the
   tenant's min_rupees_at_stake_for_planner). An ineligible gap never reaches the model -- the Cost
   Governor skips it -- so it has no model trajectory to record or evaluate.
2. The five gaps that already had evalsets (PINNED) are always in.
3. A stratum is (gap type, node kind); node kind is nodes.type (dark_store or outlet). Every
   non-empty eligible stratum gets min(its size, FLOOR) gaps, pinned gaps counting towards it.
4. The remaining slots go to strata in proportion to their eligible size (largest remainder),
   never more than a stratum has.
5. Inside a stratum, gaps are sorted by rupees at stake (desc, then gap_id) and picked at evenly
   spaced ranks, so the selection spans the at-stake range instead of only the largest gaps.

Deterministic: same tenant (generator seed 20260912) -> same selection.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

from agents.gate.config import load_tenant
from agents.gate.store import LocalStore
from agents.planner import governor
from harness.checklists import ROOT

PINNED = ["gap_kaju_ds01", "gap_chips_ds07", "gap_tea_ds04", "gap_quinoa_out02", "gap_cola_ds07"]
FLOOR = 4
GAP_TYPES = ["online_sellby_breach", "expiry_writeoff", "stockout_risk", "slow_mover", "rebalance"]
NODE_KINDS = ["dark_store", "outlet"]


def _spread(rows: list[dict], k: int) -> list[dict]:
    """k rows at evenly spaced ranks (first and last included when k >= 2)."""
    if k <= 0:
        return []
    if k >= len(rows):
        return list(rows)
    if k == 1:
        return [rows[0]]
    idx = sorted({round(i * (len(rows) - 1) / (k - 1)) for i in range(k)})
    # rounding can collide on short lists; fill from the unused ranks in order
    for i in range(len(rows)):
        if len(idx) >= k:
            break
        if i not in idx:
            idx.append(i)
    return [rows[i] for i in sorted(idx)]


def select(data_dir: str | Path, n: int = 50) -> dict:
    store = LocalStore(data_dir)
    tenant = load_tenant()
    kinds = {r["node_id"]: r["type"] for r in store.read("nodes")}
    all_gaps = store.read("gaps")
    strata_all: dict[tuple[str, str], int] = defaultdict(int)
    strata: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for g in all_gaps:
        key = (g["type"], kinds[g["node_id"]])
        strata_all[key] += 1
        if governor.planner_eligible(g, tenant)[0]:
            strata[key].append(g)
    for rows in strata.values():
        rows.sort(key=lambda g: (-float(g["rupees_at_stake"]), g["gap_id"]))

    by_id = {g["gap_id"]: g for g in all_gaps}
    missing = [p for p in PINNED if p not in by_id or not governor.planner_eligible(by_id[p], tenant)[0]]
    if missing:
        raise SystemExit(f"select_eval_gaps: pinned gaps missing or ineligible: {missing}")

    quota = {key: min(len(rows), FLOOR) for key, rows in strata.items()}
    for p in PINNED:  # a pinned gap may push its stratum above the floor
        key = (by_id[p]["type"], kinds[by_id[p]["node_id"]])
        quota[key] = max(quota[key], sum(1 for q in PINNED if (by_id[q]["type"], kinds[by_id[q]["node_id"]]) == key))
    left = n - sum(quota.values())
    if left < 0:
        raise SystemExit(f"select_eval_gaps: floors need {n - left} gaps, more than n={n}")
    room = {key: len(rows) - quota[key] for key, rows in strata.items() if len(rows) > quota[key]}
    total = sum(len(strata[k]) for k in room)
    shares = {k: left * len(strata[k]) / total for k in room} if total else {}
    extra = {k: min(room[k], int(s)) for k, s in shares.items()}
    for k in sorted(shares, key=lambda k: (-(shares[k] - int(shares[k])), k)):
        if sum(extra.values()) >= left:
            break
        if extra[k] < room[k]:
            extra[k] += 1
    for k, e in extra.items():
        quota[k] += e

    picked: list[dict] = []
    for key in sorted(strata, key=lambda k: (GAP_TYPES.index(k[0]), NODE_KINDS.index(k[1]))):
        rows = strata[key]
        pins = [g for g in rows if g["gap_id"] in PINNED]
        rest = [g for g in rows if g["gap_id"] not in PINNED]
        chosen = pins + _spread(rest, quota[key] - len(pins))
        chosen.sort(key=lambda g: (-float(g["rupees_at_stake"]), g["gap_id"]))
        picked += [{"gap_id": g["gap_id"], "type": g["type"], "node_kind": key[1], "node_id": g["node_id"], "sku": g["sku"], "rupees_at_stake": g["rupees_at_stake"], "pinned": g["gap_id"] in PINNED} for g in chosen]

    manifest = json.loads((store.root / "manifest.json").read_text(encoding="utf-8"))
    empty = [f"{t}/{k}" for t in GAP_TYPES for k in NODE_KINDS if strata_all.get((t, k), 0) and not strata.get((t, k))]
    absent = [f"{t}/{k}" for t in GAP_TYPES for k in NODE_KINDS if not strata_all.get((t, k), 0)]
    return {
        "selected_at": date.today().isoformat(),
        "label": f"seeded (synthetic tenant, generator seed {manifest['seed']})",
        "tenant": {"seed": manifest["seed"], "as_of": manifest["as_of"], "gaps_total": len(all_gaps)},
        "n": len(picked),
        "rule": (__doc__ or "").split("The rule (also written into the output so the selection can be checked against it):", 1)[1].split("Deterministic:", 1)[0].strip(),
        "floor_per_stratum": FLOOR,
        "pinned": PINNED,
        "strata": {f"{t}/{k}": {"gaps": strata_all.get((t, k), 0), "eligible": len(strata.get((t, k), [])), "selected": sum(1 for p in picked if p["type"] == t and p["node_kind"] == k)} for t in GAP_TYPES for k in NODE_KINDS if strata_all.get((t, k), 0)},
        "not_covered": {
            "strata_with_gaps_but_none_eligible": empty,
            "strata_with_no_gaps_in_tenant": absent,
        },
        "gaps": picked,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--data", default=os.environ.get("TAAL_DATA_DIR", ".local/data"))
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    sel = select(args.data, args.n)
    out = Path(args.out) if args.out else ROOT / "eval" / "raw" / f"planner_evalset_selection_{sel['selected_at']}.json"
    out.write_text(json.dumps(sel, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"select_eval_gaps: {sel['n']} gaps -> {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")
    for k, v in sel["strata"].items():
        print(f"  {k:32s} gaps={v['gaps']:4d} eligible={v['eligible']:4d} selected={v['selected']:3d}")
    print(f"  not covered: {sel['not_covered']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
