"""Snapshot the 60-second beat on the seeded tenant, through the API test client (no network, no
model call): the Tea play's counterfactuals, one Approve, Ravi's chat order, and the Measure that
the app's "Fast-forward one day" button runs. Run after `make generate`:

    uv run python -m harness.tea_beat_snapshot [--out eval/raw/tea_recorded_beat_<YYYY-MM-DD>.json]

Everything here is SYNTHETIC; one order cannot prove an effect, so Measure reports inconclusive.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

PLAY_ID = "play_tea_ds04_v1"


def snapshot(data_dir: str) -> dict:
    os.environ["TAAL_DATA_DIR"] = data_dir
    os.environ["TAAL_SANDBOX_DIR"] = tempfile.mkdtemp(prefix="taal-beat-")
    as_of = json.loads((Path(data_dir) / "manifest.json").read_text())["as_of"]
    os.environ["TAAL_NOW"] = f"{as_of}T03:30:00Z"
    from fastapi.testclient import TestClient

    from services.api.main import app

    c = TestClient(app)
    h = {"X-Taal-Visitor": "tea-beat-snapshot"}
    hj = {**h, "Accept": "application/json"}
    play = c.get(f"/plays/{PLAY_ID}", headers=h).json()
    gap = c.get(f"/gaps/{play['gap_id']}", headers=h).json()
    approve = c.post("/approve", json={"play_id": PLAY_ID}, headers=h).json()
    forecast = {k: v for k, v in approve["forecast"].items() if k != "series"}
    offer = c.post("/chat", json={"session_id": "CUST-RAVI:web", "text": "Any offers today?"}, headers=hj).json()[0]
    order = c.post("/chat", json={"session_id": "CUST-RAVI:web", "text": "Yes please, I'll take it"}, headers=hj).json()[0]
    c.post("/measure", headers=h)
    outcome = next(o for o in c.get("/outcomes", headers=h).json() if o["play_id"] == PLAY_ID)
    return {
        "what": "Tea beat on the seeded tenant via the API test client: GET play, POST /approve, CUST-RAVI chats and orders one Darjeeling Tea 100G, then POST /measure (the app's 'Fast-forward one day'). One synthetic order, so inconclusive.",
        "data_label": "SYNTHETIC",
        "play": {
            "play_id": PLAY_ID, "source": play.get("source"), "mechanic": play["mechanic"], "mechanic_params": play.get("mechanic_params"),
            "audience": {k: play["audience"].get(k) for k in ("segment_ids", "size_before_consent", "size_after_consent")},
            "expected_outcome": play["expected_outcome"], "counterfactuals": play["counterfactuals"],
            # the three bars are net write-off exposure: blanket_markdown_inr is the loss under a blanket markdown,
            # play_net_inr the (negative) net of the play, so the play wins by blanket + play_net
            "play_beats_blanket_markdown_by_inr": round(play["counterfactuals"]["blanket_markdown_inr"] + play["counterfactuals"]["play_net_inr"], 2),
        },
        "gap": {"units_at_risk": gap.get("units_at_risk"), "rupees_at_stake": gap.get("rupees_at_stake"), "online_sellby_date": gap.get("deadline_date")},
        "approve": {"assignment": approve["assignment"], "offers_written": approve["offers_written"], "forecast": forecast},
        "ravi": {"offer_text": offer["text"], "order_text": order["text"]},
        "outcome": outcome,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=os.environ.get("TAAL_DATA_DIR", ".local/data"))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    snap = snapshot(args.data)
    text = json.dumps(snap, indent=1, ensure_ascii=False) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
