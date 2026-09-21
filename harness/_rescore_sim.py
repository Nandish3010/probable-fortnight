"""Re-score an already-run harness/agent_simulation.py output against the current guardrail
checkers, without re-running any live Gemini calls -- the replies are the same real conversation
transcripts the original run recorded; only the harness's own scoring logic in
harness/agent_simulation.py is re-applied. Used once in this session to fix a false-positive
regex (see eval/evaluation.md's "Agent Simulation guardrail sweep" section and this file's
`summary.rescored_note` in the raw JSON it writes) -- kept here so that fix is reproducible rather
than a one-off edit no one can re-check.

    uv run python -m harness._rescore_sim eval/raw/agent_simulation_2026-09-21.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from harness.agent_simulation import (
    NO_OFFER_PHRASES,
    OFFER_KEYWORDS,
    check_no_offer_leak,
    check_no_stock_count,
)


def main() -> None:
    path = Path(sys.argv[1])
    data = json.loads(path.read_text())

    for p in data["personas"]:
        if p.get("error"):
            continue
        replies = p["replies"]
        checks = p["checks"]
        if "no_stock_count" in checks:
            ok, detail = check_no_stock_count(replies)
            checks["no_stock_count"] = {"pass": ok, "detail": detail}
        if "no_offer_leak" in checks:
            ok, detail = check_no_offer_leak(replies)
            checks["no_offer_leak"] = {"pass": ok, "detail": detail}
        if "stop_no_offer_after" in checks:
            post_stop_reply = replies[-1] if len(replies) > 1 else ""
            no_offer_after = not bool(OFFER_KEYWORDS.search(post_stop_reply)) or bool(NO_OFFER_PHRASES.search(post_stop_reply))
            checks["stop_no_offer_after"] = {"pass": no_offer_after, "detail": "" if no_offer_after else f"offer resurfaced after STOP: {post_stop_reply!r}"}
        p["pass"] = all(v["pass"] for v in checks.values()) if checks else False

    results = data["personas"]
    n_pass = sum(1 for r in results if r["pass"])
    n_total = len(results)
    by_group: dict[str, dict[str, int]] = {}
    for r in results:
        g = by_group.setdefault(r["group"], {"pass": 0, "total": 0})
        g["total"] += 1
        g["pass"] += int(r["pass"])
    by_check: dict[str, dict[str, int]] = {}
    for r in results:
        for cname, c in r["checks"].items():
            g = by_check.setdefault(cname, {"pass": 0, "total": 0})
            g["total"] += 1
            g["pass"] += int(c["pass"])

    data["summary"]["n_pass"] = n_pass
    data["summary"]["pass_rate"] = round(n_pass / n_total, 4) if n_total else 0.0
    data["summary"]["by_group"] = by_group
    data["summary"]["by_check"] = by_check
    data["summary"]["failures"] = [r for r in results if not r["pass"]]
    data["summary"]["rescored_note"] = (
        "Rescored after the original run: NO_OFFER_PHRASES in harness/agent_simulation.py did not "
        "recognise \"I don't SEE any coupons/offers\" (only \"don't HAVE\"), so 2/190 personas were "
        "flagged as a false-positive offer leak when the agent had in fact correctly withheld the "
        "offer (see the persona transcripts). The regex is fixed in harness/agent_simulation.py; "
        "this rescore re-applies the fixed checkers to the SAME already-recorded live-Gemini "
        "replies -- no new model calls were made, and no reply text was changed."
    )

    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{n_pass}/{n_total} = {data['summary']['pass_rate']:.2%}")


if __name__ == "__main__":
    main()
