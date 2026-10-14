"""Aggregate the per-run records of one adversarial eval directory into counts and markdown tables.

    uv run python -m harness.adversarial_summary eval/raw/adversarial_2026-10-14

Reads <dir>/{planner,chat,vision}/*.json only; writes <dir>/summary.json and <dir>/summary.md. No model call.
A run counts as scored when its verdict is PASS, FAIL, FALSE_REFUSAL or NO_MODEL_PLAY; INVALID, NOT_RUN and
HARNESS_FAILURE runs are listed separately and excluded from every rate.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

SCORED = ("PASS", "FAIL", "FALSE_REFUSAL", "NO_MODEL_PLAY")


def load(d: Path) -> list[dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for a in ("planner", "chat", "vision") for p in sorted((d / a).glob("*.json"))]


def aggregate(runs: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"areas": {}, "cases": {}}
    for area in ("planner", "chat", "vision"):
        rs = [r for r in runs if r["area"] == area]
        att = [r for r in rs if r["kind"] == "attack"]
        ctl = [r for r in rs if r["kind"] == "control"]
        a = {
            "cases": len({r["case_id"] for r in rs}), "attack_cases": len({r["case_id"] for r in att}), "control_cases": len({r["case_id"] for r in ctl}),
            "runs": len(rs), "attack_runs": len(att), "control_runs": len(ctl),
            "unscored": {v: sum(1 for r in rs if r["verdict"] == v) for v in ("INVALID", "NOT_RUN", "HARNESS_FAILURE") if any(r["verdict"] == v for r in rs)},
            "attack_pass": sum(1 for r in att if r["verdict"] == "PASS"), "attack_fail": sum(1 for r in att if r["verdict"] == "FAIL"),
            "attack_no_model_play": sum(1 for r in att if r["verdict"] == "NO_MODEL_PLAY"),
            "control_pass": sum(1 for r in ctl if r["verdict"] == "PASS"), "control_false_refusal": sum(1 for r in ctl if r["verdict"] == "FALSE_REFUSAL"), "control_fail": sum(1 for r in ctl if r["verdict"] == "FAIL"),
        }
        if area == "planner":
            a["stopped_by_guardrail_layer"] = sum(1 for r in att if r["verdict"] == "PASS" and r.get("stopped_by") == "guardrail_layer")
            a["stopped_model_ignored"] = sum(1 for r in att if r["verdict"] == "PASS" and r.get("stopped_by") == "model_ignored")
            a["draft_carried_injected_value"] = sum(1 for r in att if any(x["present"] for x in r.get("attempts") or []))
        if area == "vision":
            a["routing"] = {k: sum(1 for r in att if r["verdict"] == "PASS" and r.get("routing") == k) for k in sorted({r.get("routing") for r in att if r["verdict"] == "PASS" and r.get("routing")})}
        if area == "chat":
            screened = [r for r in rs if r.get("model_armor")]
            a["armor_blocked_attack_runs"] = sum(1 for r in att if any(m["blocked"] for m in r.get("model_armor") or []))
            a["armor_blocked_control_runs"] = sum(1 for r in ctl if any(m["blocked"] for m in r.get("model_armor") or []))
            a["armor_error_turns"] = sum(1 for r in screened for m in r["model_armor"] if m["source"] != "model_armor")
            a["armor_blocked_and_agent_failed"] = sum(1 for r in att if r["verdict"] == "FAIL" and any(m["blocked"] for m in r.get("model_armor") or []))
            a["armor_missed_and_agent_failed"] = sum(1 for r in att if r["verdict"] == "FAIL" and not any(m["blocked"] for m in r.get("model_armor") or []))
        out["areas"][area] = a
    by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in runs:
        by[r["case_id"]].append(r)
    for cid, rs in sorted(by.items()):
        rs.sort(key=lambda r: r["run"])
        c: dict[str, Any] = {"area": rs[0]["area"], "kind": rs[0]["kind"], "verdicts": [r["verdict"] for r in rs]}
        if rs[0]["area"] == "chat":
            c["armor_blocked"] = [[m["blocked"] for m in (r.get("model_armor") or [])] for r in rs]
        if rs[0]["area"] == "planner":
            c["stopped_by"] = [r.get("stopped_by") for r in rs]
        if rs[0]["area"] == "vision":
            c["routing"] = [r.get("routing") for r in rs]
        out["cases"][cid] = c
    return out


def markdown(agg: dict[str, Any]) -> str:
    lines = ["| Case | Kind | Run 1 | Run 2 | Run 3 | Notes |", "|---|---|---|---|---|---|"]
    for cid, c in agg["cases"].items():
        v = c["verdicts"] + [""] * (3 - len(c["verdicts"]))
        if c["area"] == "chat":
            note = "Model Armor blocked: " + ", ".join("/".join("yes" if b else "no" for b in bl) for bl in c["armor_blocked"])
        elif c["area"] == "planner":
            note = "stopped by: " + ", ".join(str(s) for s in c["stopped_by"])
        else:
            note = "routing: " + ", ".join(str(s) for s in c["routing"])
        lines.append(f"| {cid} | {c['kind']} | {v[0]} | {v[1]} | {v[2]} | {note} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    d = Path(argv[1])
    agg = aggregate(load(d))
    (d / "summary.json").write_text(json.dumps(agg, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (d / "summary.md").write_text(markdown(agg), encoding="utf-8")
    print(json.dumps(agg["areas"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
