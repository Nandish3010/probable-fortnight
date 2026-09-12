"""Regenerate web/mocks/*.json from the real API in a throwaway sandbox so mock mode shows the
same shapes and numbers as the live paths. Run after `make generate`: `make mocks`."""
from __future__ import annotations

import json
import os
import shutil
import sys

from harness.checklists import ROOT

DEMO = {"gap_chips_ds07", "gap_tea_ds04", "gap_cola_ds07", "gap_cola_ds02", "gap_kaju_ds01", "gap_kaju_ds03", "gap_quinoa_out02"}


def main() -> int:
    os.environ["TAAL_SANDBOX_DIR"] = str(ROOT / ".local" / "mock_sandbox")
    from fastapi.testclient import TestClient

    from agents.customer.chat import reset_sessions
    from services.api.main import app

    reset_sessions()
    c = TestClient(app, headers={"X-Taal-Visitor": "mock-builder"})
    c.post("/reset")
    out: dict = {"health": c.get("/health").json()}
    gaps = c.get("/gaps", params={"limit": 200}).json()
    out["gaps"] = [g for g in gaps if g["gap_id"] in DEMO] + [g for g in gaps if g["gap_id"] not in DEMO][:13]
    out["plays"] = c.get("/plays").json()
    out["policy"] = c.get("/policy").json()
    out["approve"] = c.post("/approve", json={"play_id": "play_chips_ds07_v1"}).json()
    chips = next(p for p in out["plays"] if p["play_id"] == "play_chips_ds07_v1")
    out["events"] = c.get("/events/" + chips["trace_ref"].split("/", 1)[1]).json()
    out["rerun"] = c.post("/rerun", json={"gap_id": "gap_tea_ds04", "policy_text": (ROOT / "fixtures" / "policy_v2.txt").read_text(encoding="utf-8"), "policy_version": "v2"}).json()
    out["capture"] = c.post("/capture", json={"node_id": "DS-07", "photo_ref": "fixtures/photos/pallet_01.jpg"}).json()
    out["execution"] = c.post("/execution", json={"play_id": "play_chips_ds07_v1", "node_id": "DS-07", "steps_done": ["print_tag"]}).json()

    def turns(session: str, texts: list[str]) -> list[dict]:
        return [c.post("/chat", json={"session_id": session, "text": t}, headers={"Accept": "application/json"}).json()[0] for t in texts]

    out["chat"] = {
        "greeting": turns("CUST-MEENA:web", ["Any offers today?"]), "cola_zero": turns("CUST-MEENA:web", ["Do you have Cola Zero?"]),
        "browse": turns("CUST-MEENA:web", ["What all do you have?"]), "chips": turns("CUST-MEENA:web", ["Tell me for chips"]),
        "order": turns("CUST-MEENA:web", ["add:SKU-MASALA-CHIPS-200G"]), "stop": turns("CUST-MEENA:web", ["STOP"]), "default": turns("CUST-RAVI:web", ["hello"]),
    }
    c.post("/approve", json={"play_id": "play_kaju_ds03_v1"})
    c.post("/measure")
    out["outcomes"] = c.get("/outcomes").json()
    for name, obj in out.items():
        (ROOT / "web" / "mocks" / f"{name}.json").write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    c.post("/reset")
    shutil.rmtree(ROOT / ".local" / "mock_sandbox", ignore_errors=True)
    print(f"mocks: {len(out)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
