"""Measure POST /rerun end-to-end against a running Taal API: N independent live re-plans, timed
from the client, on one gap.

    uv run python -m harness.measure_live_rerun --api http://localhost:8080 --runs 10 \\
        --gap gap_chips_ds07 --out eval/raw/planner_live_rerun_<YYYY-MM-DD>

Each run uses a fresh random `X-Taal-Visitor` (so runs never share a rate-limit bucket or a
sandbox) and: reads the visitor's own policy text via GET /policy, unchanged; POSTs /rerun and
times the 202; opens the returned SSE stream and times the first streamed record and the
`event: done` message (both measured from the moment the POST was sent); reads the terminal done
payload off that stream; and separately re-reads GET /events/{run_id} for the trace's own
`kind: run_summary` record, the one place token usage lives.

Refuses to write into a directory named `planner_live_rerun_*` unless every run's own 202 body
named backend "vertex" -- that prefix is reserved for a real measurement and there is no override
for it. Anywhere else, a non-"vertex" backend still needs `--allow-stub` (to exercise this tool's
own mechanics only) and the written summary is labelled synthetic, never a Gemini latency.
"""
from __future__ import annotations

import argparse
import json
import math
import secrets
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RESERVED_PREFIX = "planner_live_rerun_"
DONE_FIELDS = ("status", "source", "planner_source", "fallback_reason", "iterations", "elapsed_ms")


class MeasureAbort(Exception):
    """An expected, clearly-explained refusal -- caught once in main() and printed as one line."""


def _headers(vid: str, json_body: bool = False) -> dict[str, str]:
    h = {"X-Taal-Visitor": vid, "Accept": "application/json"}
    if json_body:
        h["Content-Type"] = "application/json"
    return h


def _get_json(url: str, headers: dict[str, str], timeout: float) -> Any:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise MeasureAbort(f"GET {url} -> {e.code}: {e.read().decode(errors='replace')[:300]}") from e


def _post_json(url: str, headers: dict[str, str], payload: dict[str, Any], timeout: float) -> tuple[int, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise MeasureAbort(f"POST {url} -> {e.code}: {e.read().decode(errors='replace')[:300]}") from e


def _consume_sse(url: str, headers: dict[str, str], t0: float, timeout: float) -> dict[str, Any]:
    """Read one SSE response line by line (stdlib only, matching harness/sweep_live.py). A plain
    trace record is one `data: ...` line then a blank line; the terminal message is `event: done`
    then `data: ...` then a blank line (exactly services/api/main.py::_live_follow_events' own
    framing). A `:` line is a keepalive comment (standard SSE), skipped, and never counted as a
    streamed record."""
    req = urllib.request.Request(url, headers=headers, method="GET")
    records = 0
    first_record_s: float | None = None
    done_payload: dict[str, Any] | None = None
    done_s: float | None = None
    event_name: str | None = None
    data_lines: list[str] = []
    with urllib.request.urlopen(req, timeout=timeout) as r:
        while True:
            raw = r.readline()
            if not raw:
                break  # connection closed by the server without a done message
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            if line == "":
                if data_lines:
                    data = "\n".join(data_lines)
                    if event_name == "done":
                        done_payload = json.loads(data)
                        done_s = time.monotonic() - t0
                        event_name, data_lines = None, []
                        break
                    records += 1
                    if first_record_s is None:
                        first_record_s = time.monotonic() - t0
                event_name, data_lines = None, []
                continue
            if line.startswith(":"):
                continue
            if line.startswith("event:"):
                event_name = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:"):].strip())
    if done_payload is None:
        raise MeasureAbort(f"SSE stream {url} ended without an 'event: done' message")
    return {"streamed_record_count": records, "time_to_first_record_s": first_record_s, "time_to_done_s": done_s, "done_payload": done_payload}


def _run_summary_usage(events: list[dict[str, Any]]) -> dict[str, Any]:
    summary = next((e for e in reversed(events) if e.get("kind") == "run_summary"), None)
    return (summary or {}).get("usage") or {}


def run_once(api: str, gap_id: str, run_index: int, timeout: float) -> dict[str, Any]:
    vid = f"liverun{secrets.token_hex(4)}"
    policy = _get_json(f"{api}/policy", _headers(vid), timeout)
    policy_text = policy["text"]

    t0 = time.monotonic()
    status, accepted = _post_json(f"{api}/rerun", _headers(vid, json_body=True), {"gap_id": gap_id, "policy_text": policy_text}, timeout)
    time_to_202_s = time.monotonic() - t0
    if status != 202:
        raise MeasureAbort(f"POST /rerun expected 202, got {status}: {accepted}")

    sse = _consume_sse(f"{api}{accepted['stream_url']}", _headers(vid), t0, timeout)
    events_resp = _get_json(f"{api}/events/{accepted['run_id']}", _headers(vid), timeout)
    usage = _run_summary_usage(events_resp.get("events") or [])
    done = sse["done_payload"]

    return {
        "run": run_index, "visitor": vid, "gap_id": gap_id, "run_id": accepted["run_id"],
        "backend": accepted.get("backend"), "configured_deadline_s": accepted.get("deadline_s"),
        "time_to_202_s": round(time_to_202_s, 3),
        "time_to_first_record_s": round(sse["time_to_first_record_s"], 3) if sse["time_to_first_record_s"] is not None else None,
        "time_to_done_s": round(sse["time_to_done_s"], 3),
        "streamed_record_count": sse["streamed_record_count"],
        "done": {k: done.get(k) for k in DONE_FIELDS},
        "token_usage": usage,
    }


def _nearest_rank(values: list[float], pct: float) -> float:
    """Nearest-rank percentile: sort ascending, take the ceil(pct/100 * n)-th value (1-indexed,
    clamped to [1, n]). Method stated here, not just used, so a reader can check it without
    reading this file."""
    if not values:
        raise ValueError("no values to take a percentile of")
    s = sorted(values)
    rank = max(1, min(len(s), math.ceil(pct / 100.0 * len(s))))
    return s[rank - 1]


METHOD = (
    "p50/p95 are nearest-rank (sort ascending, take the ceil(p/100*n)-th value, 1-indexed) over "
    "each run's time_to_done_s -- client wall-clock seconds from the moment POST /rerun was sent "
    "to the 'event: done' SSE message. fallback_rate is the share of runs whose done payload's "
    "source is 'deterministic_rules'. mean_tokens is the mean of each run's run_summary "
    "usage.total_token_count (from GET /events/{run_id}), over the runs that reported one."
)


def build_summary(api: str, gap_id: str, runs: list[dict[str, Any]], label: str) -> dict[str, Any]:
    n = len(runs)
    wall_times = [r["time_to_done_s"] for r in runs]
    fallback_n = sum(1 for r in runs if r["done"].get("source") == "deterministic_rules")
    tokens = [r["token_usage"].get("total_token_count") for r in runs]
    tokens = [t for t in tokens if isinstance(t, int | float) and not isinstance(t, bool)]
    backends = sorted({r["backend"] for r in runs})
    return {
        "measured_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "api": api, "gap_id": gap_id, "n": n, "backend": backends[0] if len(backends) == 1 else backends,
        "label": label, "method": METHOD,
        "p50_wall_s": _nearest_rank(wall_times, 50), "p95_wall_s": _nearest_rank(wall_times, 95),
        "fallback_n": fallback_n, "fallback_rate": round(fallback_n / n, 4) if n else None,
        "mean_tokens": round(sum(tokens) / len(tokens), 1) if tokens else None,
        "n_runs_with_token_usage": len(tokens),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default="http://localhost:8090", help="base URL of a running Taal API (default: http://localhost:8090)")
    ap.add_argument("--runs", type=int, default=10, help="independent live re-plans to measure (default 10)")
    ap.add_argument("--gap", default="gap_chips_ds07", help="gap_id to re-plan (default gap_chips_ds07)")
    ap.add_argument("--out", required=True, help="output directory, e.g. eval/raw/planner_live_rerun_2026-09-27")
    ap.add_argument("--timeout", type=float, default=120.0, help="per-request timeout in seconds (default 120)")
    ap.add_argument("--allow-stub", action="store_true", help="allow a non-'vertex' backend (to exercise this tool's own mechanics only); the summary is then labelled synthetic")
    args = ap.parse_args(argv)

    try:
        runs = [run_once(args.api, args.gap, i, args.timeout) for i in range(1, args.runs + 1)]
        backends = sorted({r["backend"] for r in runs})
        if len(backends) != 1:
            raise MeasureAbort(f"runs disagree on backend across their own 202 bodies: {backends} -- refusing to summarize a mixed-backend run set")
        backend = backends[0]
        out_dir = Path(args.out)
        reserved = out_dir.name.startswith(RESERVED_PREFIX)
        if backend != "vertex":
            if reserved:
                raise MeasureAbort(f"refusing to write into {out_dir.name!r} (starts with {RESERVED_PREFIX!r}, reserved for a real backend='vertex' measurement) -- every run's 202 body reported backend {backend!r}")
            if not args.allow_stub:
                raise MeasureAbort(f"every run's 202 body reported backend {backend!r}, not 'vertex' -- pass --allow-stub to write synthetic, harness-validation-only output anyway")
            label = "synthetic (stub backend) -- harness validation, not a Gemini latency"
        else:
            label = f"measured: {len(runs)} live re-plan run(s), local client against a running API process with backend=vertex"
        summary = build_summary(args.api, args.gap, runs, label)
    except MeasureAbort as e:
        print(f"measure_live_rerun: {e}", file=sys.stderr)
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "runs.jsonl", "w", encoding="utf-8") as f:
        for r in runs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"measure_live_rerun: wrote {out_dir} ({len(runs)} run(s), backend={backend}, label={label!r})")
    print(json.dumps({k: v for k, v in summary.items() if k != "method"}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
