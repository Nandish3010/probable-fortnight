"""Build the v4 DEV set from recorded v2 / v3 scenarios (no model call): every loss case of eval/sealed/v4/loss_analysis.md plus
controls (wins). DEV set: the v4 changes are tuned on it. Not an independent test.

    python -m eval.sealed.v4.make_dev
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
# (set, scenario id, role)
CASES = [("v3", i, "loss") for i in ("S01", "S02", "S04", "S05", "S06", "S08", "S09", "S10", "S11", "S14", "S19")] + [("v2", i, "loss") for i in ("S31", "S34", "S36")] + \
        [("v3", i, "control") for i in ("S03", "S17", "S20", "S23", "S28", "S35")]


def main() -> int:
    scen, base, before = [], {}, {}
    cache = {}
    for st in ("v2", "v3"):
        cache[st] = (json.loads((ROOT / f"eval/sealed/{st}/scenarios.json").read_text())["scenarios"], json.loads((ROOT / f"eval/sealed/{st}/baselines.json").read_text())["baselines"])
    loss = {(x["set"], x["id"]): x for x in json.loads((ROOT / "eval/sealed/v4/loss_cases.json").read_text())["all"]}
    for n, (st, sid, role) in enumerate(CASES, start=1):
        s = next(x for x in cache[st][0] if x["scenario_id"] == sid)
        b = dict(cache[st][1][sid])
        did = f"D{n:02d}"
        legal = [v["blanket_recovery_inr"] for v in b["markdown_plays"].values() if v["clears_margin_floor"]]
        b.setdefault("blanket_legal_recovery_inr", max([0.0, *legal]))
        b.setdefault("blanket20_is_floor_legal", bool(b["markdown_plays"]["20"]["clears_margin_floor"]))
        b.setdefault("upper_bound_beats_blanket20", bool(b["oracle_upper_bound_inr"] > b["blanket20_recovery_inr"]))
        scen.append({**s, "scenario_id": did, "origin": {"set": st, "scenario_id": sid, "role": role}})
        base[did] = b
        x = loss[(st, sid)]
        before[did] = {"origin": f"{st} {sid}", "role": role, "mechanic": x["mechanic"], "recovery_inr": x["recovery"], "captured": x["captured"], "turns": x["turns"], "latency_s": x["latency_s"], "beats_blanket": x["beats_blanket"], "upper_bound_inr": x["upper_bound"], "best_md_inr": x["best_md"]}
    (ROOT / "eval/sealed/v4/dev_scenarios.json").write_text(json.dumps({"label": "DEV set, tuned on; not an independent test", "scenarios": scen}, indent=1) + "\n")
    (ROOT / "eval/sealed/v4/dev_baselines.json").write_text(json.dumps({"label": "DEV set, tuned on; not an independent test", "baselines": base}, indent=1) + "\n")
    (ROOT / "eval/sealed/v4/dev_before.json").write_text(json.dumps(before, indent=1) + "\n")
    print(len(scen), "cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
