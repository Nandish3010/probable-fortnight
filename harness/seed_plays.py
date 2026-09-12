"""Seed the demo plays into the base tenant after Sense (part of `make generate`): the Planner
runs once per demo gap so the API, the web app and the tests find plays without a model call."""
from __future__ import annotations

import asyncio
import os
import sys

from agents.planner.run import run_planner_async

DEMO_GAPS = ["gap_chips_ds07", "gap_tea_ds04", "gap_cola_ds07", "gap_cola_ds02", "gap_kaju_ds01", "gap_kaju_ds03", "gap_quinoa_out02"]


async def main_async() -> int:
    data = os.environ.get("TAAL_DATA_DIR", ".local/data")
    for gid in DEMO_GAPS:
        out = await run_planner_async(data, gid)
        print(f"seed: {gid} -> {out['status']} {out['play']['play_id'] if out['play'] else ''} ({out['iterations']} iteration(s))")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main_async()))
