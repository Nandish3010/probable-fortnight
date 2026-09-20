"""Seed the demo plays into the base tenant after Sense (part of `make generate`): the Planner
runs once per demo gap so the API, the web app and the tests find plays without a model call."""
from __future__ import annotations

import asyncio
import os
import sys

from agents.planner.run import run_planner_async

DEMO_GAPS = ["gap_chips_ds07", "gap_tea_ds04", "gap_cola_ds07", "gap_cola_ds02", "gap_kaju_ds01", "gap_kaju_ds03", "gap_quinoa_out02", "gap_blazer_ds07"]


async def seed_plays(data_dir: str) -> list[dict]:
    """Run the Planner once per demo gap; idempotent (re-approving overwrites the same play id).
    Shared by `python -m harness.seed_plays` (part of `make generate`) and tests/conftest.py, so a
    tenant built anywhere -- CI's pre-`generate` `schemas` step included -- always has the demo
    plays a contract or API test might approve or read."""
    return [await run_planner_async(data_dir, gid) for gid in DEMO_GAPS]


async def main_async() -> int:
    data = os.environ.get("TAAL_DATA_DIR", ".local/data")
    for out in await seed_plays(data):
        print(f"seed: {out['play']['gap_id'] if out['play'] else '?'} -> {out['status']} {out['play']['play_id'] if out['play'] else ''} ({out['iterations']} iteration(s))")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main_async()))
