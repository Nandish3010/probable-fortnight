"""One-off: approve two seeded plays in the real .local/data tenant so the Agent Simulation
harness (harness/agent_simulation.py) has real treated/holdout customers and live offers to test
against. Run once, before `harness/agent_simulation.py`, after `make generate`:

    cp -r .local/data .local/data_before_approve   # the harness's "before the play" state
    uv run python -m harness._approve_for_sim       # mutates .local/data to "after" (approved)

Uses TAAL_MODEL_BACKEND=stub (the default) deliberately: approve()'s BigQuery copy-generation path
only runs when the backend is "vertex", and this step only needs the deterministic templated copy
and the real assignment/offer rows it always writes -- not a live model call.
"""
from __future__ import annotations

import json
from datetime import datetime

from agents.gate.config import load_tenant
from agents.gate.store import LocalStore
from services.api.approve import approve

PLAYS = ["play_chips_ds07_v1", "play_quinoa_out02_v1"]


def main() -> None:
    store = LocalStore(".local/data")
    tenant = load_tenant()
    as_of = json.loads((store.root / "manifest.json").read_text())["as_of"]
    now = datetime.fromisoformat(f"{as_of}T03:30:00+00:00")

    for play_id in PLAYS:
        out = approve(store, tenant, play_id, now, approved_by="agent_simulation_harness")
        print(play_id, out.get("status"), out.get("source"), out.get("note"))

    assigns = [a for a in store.read("play_assignments") if a["play_id"] in PLAYS]
    by_play: dict[str, dict[str, list[str]]] = {}
    for a in assigns:
        by_play.setdefault(a["play_id"], {"treated": [], "holdout": []})[a["arm"]].append(a["customer_id"])
    for pid, d in by_play.items():
        print(pid, "treated:", len(d["treated"]), "holdout:", len(d["holdout"]))


if __name__ == "__main__":
    main()
