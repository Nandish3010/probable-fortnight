"""Seed the demo plays into the base tenant after Sense (part of `make generate`): the Planner
runs once per demo gap so the API, the web app and the tests find plays without a model call.

The flagship gap (FLAGSHIP_GAP) is the one exception: if a committed, validated real-Gemini
recording exists for it (harness/record_flagship_traces.py + harness/recorded_traces.py), that is
seeded instead of the scripted stub -- still no model call and no network at seed time either way.
Every other demo gap always uses the scripted stub, exactly as before.
"""
from __future__ import annotations

import asyncio
import os
import sys

from agents.planner.run import run_planner_async
from harness.recorded_traces import seed_from_recording

DEMO_GAPS = ["gap_chips_ds07", "gap_tea_ds04", "gap_cola_ds07", "gap_cola_ds02", "gap_kaju_ds01", "gap_kaju_ds03", "gap_quinoa_out02"]
FLAGSHIP_GAP = "gap_chips_ds07"


async def _seed_one(data_dir: str, gap_id: str) -> dict:
    if gap_id == FLAGSHIP_GAP:
        result, message = seed_from_recording(data_dir, gap_id)
        print(f"seed: {message}")
        if result is not None:
            return result
    return await run_planner_async(data_dir, gap_id)


async def seed_plays(data_dir: str) -> list[dict]:
    """Run the Planner once per demo gap (the flagship instead seeded from a recording when one
    validates -- see _seed_one); idempotent (re-approving overwrites the same play id). Shared by
    `python -m harness.seed_plays` (part of `make generate`) and tests/conftest.py, so a tenant
    built anywhere -- CI's pre-`generate` `schemas` step included -- always has the demo plays a
    contract or API test might approve or read. The flagship is planned first (DEMO_GAPS' own
    order), so the store still has no plays in it yet when _seed_one runs for it -- the same state
    harness/record_flagship_traces.py itself records against."""
    return [await _seed_one(data_dir, gid) for gid in DEMO_GAPS]


async def main_async() -> int:
    data = os.environ.get("TAAL_DATA_DIR", ".local/data")
    for out in await seed_plays(data):
        print(f"seed: {out['play']['gap_id'] if out['play'] else '?'} -> {out['status']} {out['play']['play_id'] if out['play'] else ''} ({out['iterations']} iteration(s))")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main_async()))
