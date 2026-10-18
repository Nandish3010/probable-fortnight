"""Per-case before/after for a v4 DEV round (before = the recorded v2/v3 run of the same scenario). DEV set, tuned on; not an independent test.

    python -m eval.sealed.v4.dev_report eval/raw/sealed_v4_dev_<n>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def main(argv: list[str]) -> int:
    out = Path(argv[0])
    before = json.loads((ROOT / "eval/sealed/v4/dev_before.json").read_text())
    base = json.loads((ROOT / "eval/sealed/v4/dev_baselines.json").read_text())["baselines"]
    res = json.loads((out / "results.json").read_text())
    runs = {p.stem: json.loads(p.read_text()) for p in sorted((out / "runs").glob("D[0-9][0-9].json"))}
    rows, fixed, still, broken, kept = [], [], [], [], []
    for did, b in before.items():
        r = runs.get(did, {})
        valid = r.get("verdict") == "VALID" and r.get("outcome") == "model_play"
        rec = r.get("recovery_inr", 0.0) if valid else 0.0
        ub = base[did]["oracle_upper_bound_inr"]
        cap = rec / ub if ub else None
        was_loss = b["role"] == "loss"
        now_ok = valid and cap is not None and cap >= 0.9 and rec >= b["best_md_inr"] - 1.0
        d = rec - b["recovery_inr"]
        status = ("FIXED" if now_ok else "STILL LOST") if was_loss else ("kept" if (valid and rec >= b["recovery_inr"] * 0.98 - 1.0 and (rec > base[did]["blanket20_recovery_inr"]) == b["beats_blanket"]) else "NEWLY BROKEN" if valid else "INVALID")
        (fixed if status == "FIXED" else still if status == "STILL LOST" else broken if status in ("NEWLY BROKEN", "INVALID") else kept).append(did)
        calls = r.get("model_calls") or []
        rows.append(f"| {did} | {b['origin']} | {b['role']} | {b['mechanic']} -> {r.get('mechanic')} | {b['recovery_inr']:.2f} -> {rec:.2f} ({d:+.2f}) | {b['captured']:.2f} -> {cap if cap is None else round(cap, 2)} | {b['turns']} -> {len(calls)} | {b['latency_s']} -> {round((r.get('elapsed_ms') or 0) / 1000, 1)} | {r.get('verdict')} | {status} |")
    m = res["metrics"]
    v4 = m["v4"]
    n_inv = sum(1 for r in runs.values() if r.get("verdict") != "VALID")
    head = (f"v4 DEV ROUND {out.name.rsplit('_', 1)[-1]} (dev set, tuned on; not an independent test): {len(before)} cases ({sum(b['role']=='loss' for b in before.values())} loss + {sum(b['role']=='control' for b in before.values())} control); "
            f"fixed {len(fixed)}, still lost {len(still)}, controls kept {len(kept)}, newly broken/invalid {len(broken)} ({', '.join(broken) or 'none'}); mean model calls {v4['model_turns_per_run']['mean']:.2f} (v3 6.06), mean prompt tokens {v4['prompt_tokens_per_run_mean']:.0f} (v3 51,097), "
            f"p50/p95 latency {m['latency_s']['p50']:.1f}/{m['latency_s']['p95']:.1f} s (v3 31.3/42.3), violations {m['guardrail_violations_reaching_approve']}, invalid {n_inv}, spend ${res['meta']['spent_usd']}.")
    text = ["# DEV round (dev set, tuned on; not an independent test)", "", head, "", f"Before = the recorded v2/v3 run of the same scenario (old code). Code head {res['meta']['git_head'][:10]} (working tree), prompt sha {res['meta']['planner_prompt_sha256'][:12]}, thinking {res['meta']['thinking']}.", "",
            "| id | origin | role | mechanic | recovery before -> after | captured of upper bound | model turns | latency s | verdict | status |", "|---|---|---|---|---|---|---|---|---|---|", *rows, ""]
    (out / "summary_cases.md").write_text("\n".join(text) + "\n", encoding="utf-8")
    (out / "round_line.txt").write_text(head + "\n", encoding="utf-8")
    print(head)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
