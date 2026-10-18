"""Offline loss analysis of recorded sealed runs (no model call). Writes eval/sealed/v4/loss_analysis.md and loss_cases.json.

    python -m eval.sealed.v4.loss_analysis

A "loss" = the accepted play recovered less than the best markdown the margin floor allows, or captured < 0.9 of the estimator
upper bound (larger of the best allowed markdown and the oracle's best legal non-markdown play). Cases where only the (floor-illegal)
blanket 20% figure was higher are listed apart: the model did not lose to a legal alternative there.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MD = Path("/Users/NS/AI_builder_taal/worktrees/markdown")
SETS = {
    "v2": (ROOT / "eval/raw/sealed_v2_2026-10-19", ROOT / "eval/sealed/v2"),
    "v3": (MD / "eval/raw/sealed_v3_2026-10-19", ROOT / "eval/sealed/v3"),
}
OLD_TOL = lambda best: max(500.0, 0.05 * abs(best))  # noqa: E731
NEW_TOL = lambda best: max(50.0, 0.02 * abs(best))  # noqa: E731


def load(name: str) -> list[dict]:
    raw, base = SETS[name]
    b = json.loads((base / "baselines.json").read_text())["baselines"]
    sc = {s["scenario_id"]: s for s in json.loads((base / "scenarios.json").read_text())["scenarios"]}
    rows = []
    for p in sorted((raw / "runs").glob("S[0-9][0-9].json")):
        r = json.loads(p.read_text())
        if r.get("verdict") != "VALID" or r.get("outcome") != "model_play":
            continue
        a, s = b[r["scenario_id"]], sc[r["scenario_id"]]
        rec, md, ub = r["recovery_inr"], a["best_markdown_play_recovery_inr"], a["oracle_upper_bound_inr"]
        md_legal = md if md > 0 else 0.0
        rows.append({
            "set": name, "id": r["scenario_id"], "gap_type": s["gap"]["type"], "units": s["gap"]["units_at_risk"], "days": s["gap"]["days_to_deadline"], "margin_pct": s["features"]["margin_pct_of_price"],
            "mechanic": r["mechanic"], "recovery": rec, "best_md": md_legal, "best_md_pct": a["best_markdown_play_pct"], "ref_best": a["best_nonmarkdown_reference_inr"], "ref_class": a["best_nonmarkdown_reference_class"],
            "upper_bound": ub, "captured": rec / ub if ub > 0 else None, "blanket20": a["blanket20_recovery_inr"], "gap_to_md": round(max(0.0, md_legal - rec) if md_legal > 0 else 0.0, 2), "gap_to_ub": round(ub - rec, 2),
            "turns": len(r["model_calls"]), "latency_s": round((r["elapsed_ms"] or 0) / 1000, 1), "first_accepted": r["first_proposal_accepted"], "attempts": r["propose_play_attempts"],
            "old_tol_would_reject": md_legal - rec > OLD_TOL(md_legal) if md_legal > 0 else False, "new_tol_would_reject": md_legal - rec > NEW_TOL(md_legal) if md_legal > 0 else False,
            "beats_blanket": rec > a["blanket20_recovery_inr"], "ceiling": bool(a.get("upper_bound_beats_blanket20", ub > a["blanket20_recovery_inr"])),
        })
    return rows


def cause(x: dict) -> str:
    if x["gap_to_md"] > 1.0 and x["mechanic"] != "markdown":
        return "tolerance let a below-markdown play through" if not x["old_tol_would_reject"] else "gate failure (should have been rejected)"
    if x["gap_to_md"] > 1.0:
        return "markdown at a shallower depth than the best allowed one"
    if x["ref_best"] > x["recovery"] + 1.0 and x["mechanic"] == "markdown":
        return "chose markdown where a legal non-markdown play was better"
    if x["mechanic"] == "bundle":
        return "bundle chosen below the oracle's best legal play (variant/partner/audience choice)"
    return "other legal play below the upper bound (" + str(x["mechanic"]) + ")"


def main() -> int:
    rows = [x for n in SETS for x in load(n)]
    losses = [x for x in rows if x["gap_to_md"] > 1.0 or (x["captured"] is not None and x["captured"] < 0.9)]
    for x in losses:
        x["cause"] = cause(x)
    illegal_only = [x for x in rows if x not in losses and not x["beats_blanket"] and not x["ceiling"]]
    ceiling_missed = [x for x in rows if x["ceiling"] and not x["beats_blanket"]]
    by: dict[str, list[dict]] = {}
    for x in losses:
        by.setdefault(x["cause"], []).append(x)
    L = ["# Loss analysis of sealed v2 and v3 (offline, no model call)", "",
         "DEV material: the v4 dev set is built from these cases and tuned on; not an independent test. Runs read from `eval/raw/sealed_v2_2026-10-19/` and (read-only) `planner/markdown-option`'s `eval/raw/sealed_v3_2026-10-19/`. "
         "The v1-regression runs have no markdown baselines (v1 files) and are not used here.", "",
         f"Valid model plays analysed: {len(rows)} (v2 {sum(x['set']=='v2' for x in rows)}, v3 {sum(x['set']=='v3' for x in rows)}). Losses (recovery below the best allowed markdown, or captured < 0.9 of the upper bound): **{len(losses)}** (v2 {sum(x['set']=='v2' for x in losses)}, v3 {sum(x['set']=='v3' for x in losses)}).", "",
         "## Causes", "", "| cause | n | cases |", "|---|---|---|"]
    for c, xs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        L.append(f"| {c} | {len(xs)} | {', '.join(x['set'] + ' ' + x['id'] for x in xs)} |")
    L += ["", "## Offline replay of the gate on the recorded accepted plays", "",
          f"* Plays below the best allowed markdown by more than the OLD tolerance max(500, 5%): {sum(x['old_tol_would_reject'] for x in rows)} (the gate was live, so the recorded plays had none).",
          f"* Plays that the NEW tolerance max(50, 2%) would have sent back: **{sum(x['new_tol_would_reject'] for x in rows)}** of {len(rows)} ({', '.join(x['set'] + ' ' + x['id'] for x in rows if x['new_tol_would_reject']) or 'none'}), of {sum(x['gap_to_md'] > 1.0 for x in rows)} that were below the markdown at all.",
          f"* Rupees below the best markdown on those, total: INR {sum(x['gap_to_md'] for x in rows if x['gap_to_md'] > 1.0):,.2f}; of which the new tolerance covers INR {sum(x['gap_to_md'] for x in rows if x['new_tol_would_reject']):,.2f}.",
          "", "## Turns and latency", "",
          f"* Model turns per run: median {statistics.median(x['turns'] for x in rows)}, mean {statistics.mean(x['turns'] for x in rows):.2f} (v2 {statistics.mean(x['turns'] for x in rows if x['set']=='v2'):.2f}, v3 {statistics.mean(x['turns'] for x in rows if x['set']=='v3'):.2f}).",
          f"* Latency p50: v2 {statistics.median(x['latency_s'] for x in rows if x['set']=='v2')} s, v3 {statistics.median(x['latency_s'] for x in rows if x['set']=='v3')} s. Latency vs turns correlation: " + f"{statistics.correlation([x['turns'] for x in rows],[x['latency_s'] for x in rows]):.2f}.",
          f"* Losses average {statistics.mean(x['turns'] for x in losses):.2f} turns vs {statistics.mean(x['turns'] for x in rows if x not in losses):.2f} for non-losses.", "",
          "## Not model losses", "",
          f"* Lost to blanket 20% where the oracle upper bound is also below it (blanket is floor-illegal and generously priced; no legal play can beat it): {len(illegal_only)} ({', '.join(x['set'] + ' ' + x['id'] for x in illegal_only)}).",
          f"* Ceiling scenarios (a legal play can beat blanket 20%) that the model missed: {len(ceiling_missed)} ({', '.join(x['set'] + ' ' + x['id'] for x in ceiling_missed) or 'none'}).", "",
          "## Every loss", "", "| set | id | gap type | units | days | margin % | chosen | recovery | best allowed markdown | best legal non-markdown | upper bound | captured | gap to md | turns | latency s | cause |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for x in sorted(losses, key=lambda x: (x["set"], x["id"])):
        L.append(f"| {x['set']} | {x['id']} | {x['gap_type']} | {x['units']} | {x['days']} | {x['margin_pct']} | {x['mechanic']} | {x['recovery']:.2f} | {x['best_md']:.2f} ({x['best_md_pct']}%) | {x['ref_best']:.2f} ({x['ref_class']}) | {x['upper_bound']:.2f} | {x['captured']:.2f} | {x['gap_to_md']:.2f} | {x['turns']} | {x['latency_s']} | {x['cause']} |")
    (ROOT / "eval/sealed/v4/loss_analysis.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (ROOT / "eval/sealed/v4/loss_cases.json").write_text(json.dumps({"losses": losses, "all": rows}, indent=1) + "\n", encoding="utf-8")
    print("\n".join(L[:40]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
