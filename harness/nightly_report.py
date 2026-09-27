"""Nightly Sense/Measure run record -> eval/raw/nightly_runs/<date>.json + one README row.

    GOOGLE_APPLICATION_CREDENTIALS=... uv run python -m harness.nightly_report [--executions 3]
    make nightly-report

Read-only. No gcloud: the Cloud Run Admin API v2 and Cloud Logging v2 over REST (an
AuthorizedSession from google-auth, so no token is ever handled here), and the BigQuery Python
client for SELECTs only. Per job (taal-sense, taal-measure): the last N executions with start,
duration, status and the last 30 log lines. Per tenant, in BigQuery: forecasts rows by
(run_id, model, as_of) split into cluster- and node-level rows, gaps by type, plays /
play_assignments / play_outcomes counts, and max(date) in sales_daily.

Every number written is `measured` (a live read at `generated_at`). Row-count stability is
checked against the previous report in the same directory: a run_id whose forecast row count
changed between two reports is flagged, because Sense's run_id is a function of as_of alone
(jobs/sense/forecast.py::run_id_for), so two nights with the same as_of write the same run_id.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jobs.measure.run import NO_PLAYS_IN_BIGQUERY

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "amru-509214"
REGION = "asia-south1"
DATASET = "taal"
JOBS = ("taal-sense", "taal-measure")
LOG_LINES = 30
RUN_API = f"https://run.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}/jobs"
LOGGING_API = "https://logging.googleapis.com/v2/entries:list"
README_HEADER = (
    "# Nightly Sense/Measure run records\n\n"
    "One row per `make nightly-report` (harness/nightly_report.py). Every number is **measured**: a\n"
    "live, read-only read of the Cloud Run Admin API, Cloud Logging and BigQuery at the time shown;\n"
    "the full record is the JSON file named in the first column.\n\n"
    "| report | sense (latest) | measure (latest) | green streak sense/measure | forecast rows node/cluster | forecast run_ids | as_of | sales_daily max(date) | gaps | plays / outcomes | rows stable vs previous |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|\n"
)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

Fetch = Callable[[str, str, dict[str, Any] | None], dict[str, Any]]  # (method, url, json_body) -> json
Query = Callable[[str, str], tuple[list[dict[str, Any]], int]]  # (sql, tenant_id) -> (rows, bytes_billed)


def redact(line: str) -> str:
    """Job logs go into a public repo: never let an email address through, whatever logged it."""
    return _EMAIL.sub("<redacted-email>", line)


def _ts(s: str | None) -> datetime | None:
    if not s:
        return None
    # Cloud Run returns RFC3339 with up to nanosecond precision; datetime takes microseconds.
    s = re.sub(r"(\.\d{6})\d+", r"\1", s.replace("Z", "+00:00"))
    return datetime.fromisoformat(s)


def execution_status(ex: dict[str, Any]) -> str:
    """green | red | cancelled | running, from the execution's `Completed` condition."""
    if ex.get("cancelledCount"):
        return "cancelled"
    completed = next((c for c in ex.get("conditions", []) if c.get("type") == "Completed"), None)
    state = (completed or {}).get("state")
    if state == "CONDITION_SUCCEEDED":
        return "green"
    if state == "CONDITION_FAILED" or ex.get("failedCount"):
        return "red"
    return "running"


def summarize_execution(ex: dict[str, Any], log_lines: list[str]) -> dict[str, Any]:
    start, end = _ts(ex.get("startTime")), _ts(ex.get("completionTime"))
    return {
        "execution": ex.get("name", "").rsplit("/", 1)[-1],
        "created": ex.get("createTime"),
        "start": ex.get("startTime"),
        "completion": ex.get("completionTime"),
        "duration_s": round((end - start).total_seconds(), 1) if start and end else None,
        "status": execution_status(ex),
        "succeeded_tasks": ex.get("succeededCount", 0),
        "failed_tasks": ex.get("failedCount", 0),
        "log_tail": log_lines,
    }


def green_streak(executions: list[dict[str, Any]]) -> int:
    """Consecutive green executions, newest first; a still-running newest one is skipped."""
    n = 0
    for i, ex in enumerate(executions):
        if i == 0 and ex["status"] == "running":
            continue
        if ex["status"] != "green":
            break
        n += 1
    return n


def fetch_executions(fetch: Fetch, job: str, n: int) -> list[dict[str, Any]]:
    body = fetch("GET", f"{RUN_API}/{job}/executions?pageSize={n}", None)
    exs = body.get("executions", [])
    return sorted(exs, key=lambda e: e.get("createTime", ""), reverse=True)[:n]


def fetch_log_tail(fetch: Fetch, job: str, execution: str, n: int = LOG_LINES) -> list[str]:
    body = fetch("POST", LOGGING_API, {
        "resourceNames": [f"projects/{PROJECT}"],
        "filter": (f'resource.type="cloud_run_job" AND resource.labels.job_name="{job}" '
                   f'AND labels."run.googleapis.com/execution_name"="{execution}"'),
        "orderBy": "timestamp desc",
        "pageSize": n,
    })
    lines = []
    for e in reversed(body.get("entries", [])):
        text = e.get("textPayload")
        if text is None and "jsonPayload" in e:
            jp = e["jsonPayload"]
            text = jp.get("message") if isinstance(jp.get("message"), str) else json.dumps(jp, sort_keys=True)
        if text is None:
            continue
        lines.append(f"{e.get('timestamp', '')} {e.get('severity', 'DEFAULT')} {redact(str(text).rstrip())}")
    return lines


BQ_QUERIES: dict[str, str] = {
    "forecasts_by_run": f"""
        SELECT run_id, model, CAST(as_of AS STRING) AS as_of,
               COUNT(*) AS rows_total,
               COUNTIF(node_id IS NULL) AS cluster_rows,
               COUNTIF(node_id IS NOT NULL) AS node_rows,
               CAST(MIN(date) AS STRING) AS min_date, CAST(MAX(date) AS STRING) AS max_date
        FROM `{PROJECT}.{DATASET}.forecasts` WHERE tenant_id = @tenant_id
        GROUP BY run_id, model, as_of ORDER BY as_of DESC, run_id""",
    "gaps_by_type": f"""
        SELECT type, run_id, COUNT(*) AS n FROM `{PROJECT}.{DATASET}.gaps`
        WHERE tenant_id = @tenant_id GROUP BY type, run_id ORDER BY type""",
    "plays_by_status": f"""
        SELECT status, COUNT(*) AS n FROM `{PROJECT}.{DATASET}.plays`
        WHERE tenant_id = @tenant_id GROUP BY status ORDER BY status""",
    "play_assignments": f"SELECT COUNT(*) AS n FROM `{PROJECT}.{DATASET}.play_assignments` WHERE tenant_id = @tenant_id",
    "play_outcomes": f"SELECT COUNT(*) AS n FROM `{PROJECT}.{DATASET}.play_outcomes` WHERE tenant_id = @tenant_id",
    "sales_daily_max_date": f"""
        SELECT CAST(MAX(date) AS STRING) AS max_date, COUNT(*) AS n
        FROM `{PROJECT}.{DATASET}.sales_daily` WHERE tenant_id = @tenant_id""",
}


def bigquery_snapshot(query: Query, tenant_id: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    billed = 0
    for key, sql in BQ_QUERIES.items():
        rows, b = query(sql, tenant_id)
        billed += b or 0
        out[key] = rows
    out["bytes_billed"] = billed
    return out


def row_counts(bq: dict[str, Any]) -> dict[str, int]:
    """The counts that must stay stable night to night: forecast rows per run_id, gaps total,
    plays, play_assignments, play_outcomes."""
    counts = {f"forecasts[{r['run_id']}]": int(r["rows_total"]) for r in bq["forecasts_by_run"]}
    counts["gaps"] = sum(int(r["n"]) for r in bq["gaps_by_type"])
    counts["plays"] = sum(int(r["n"]) for r in bq["plays_by_status"])
    counts["play_assignments"] = int(bq["play_assignments"][0]["n"]) if bq["play_assignments"] else 0
    counts["play_outcomes"] = int(bq["play_outcomes"][0]["n"]) if bq["play_outcomes"] else 0
    return counts


def stability(current: dict[str, int], previous: dict[str, int] | None) -> dict[str, Any]:
    """Changed counts vs the previous report. A key present in both with a different value is a
    change; a new forecasts run_id is expected when as_of moves and is listed, not flagged."""
    if previous is None:
        return {"compared_to": None, "stable": None, "changed": {}, "new_keys": sorted(current)}
    changed = {k: {"previous": previous[k], "current": v} for k, v in current.items() if k in previous and previous[k] != v}
    return {"stable": not changed, "changed": changed, "new_keys": sorted(k for k in current if k not in previous)}


def previous_report(out_dir: Path, today: str) -> tuple[str, dict[str, Any]] | None:
    files = sorted(p for p in out_dir.glob("*.json") if re.fullmatch(r"\d{4}-\d{2}-\d{2}(_\d+)?", p.stem) and p.stem < today)
    if not files:
        return None
    return files[-1].name, json.loads(files[-1].read_text(encoding="utf-8"))


def build_report(fetch: Fetch, query: Query, tenant_id: str, n_executions: int, generated_at: str,
                 previous: tuple[str, dict[str, Any]] | None) -> dict[str, Any]:
    jobs: dict[str, Any] = {}
    for job in JOBS:
        exs = [summarize_execution(ex, fetch_log_tail(fetch, job, ex["name"].rsplit("/", 1)[-1])) for ex in fetch_executions(fetch, job, n_executions)]
        jobs[job] = {"executions": exs, "green_streak": green_streak(exs)}
    measure_latest = next((e for e in jobs["taal-measure"]["executions"] if e["status"] != "running"), None)
    bq = bigquery_snapshot(query, tenant_id)
    counts = row_counts(bq)
    stab = stability(counts, previous[1].get("row_counts") if previous else None)
    stab["compared_to"] = previous[0] if previous else None
    as_ofs = sorted({r["as_of"] for r in bq["forecasts_by_run"] if r.get("as_of")})
    return {
        "generated_at": generated_at,
        "label": "measured",
        "project": PROJECT, "region": REGION, "dataset": DATASET, "tenant_id": tenant_id,
        "method": "read-only: Cloud Run Admin API v2 + Cloud Logging v2 (REST), BigQuery SELECTs",
        "jobs": jobs,
        "bigquery": bq,
        "row_counts": counts,
        "row_count_stability": stab,
        "as_of": {
            "forecasts_as_of_values": as_ofs,
            "latest_forecasts_as_of": as_ofs[-1] if as_ofs else None,
            "sales_daily_max_date": (bq["sales_daily_max_date"] or [{}])[0].get("max_date"),
        },
        "measure_zero_plays_line_logged": bool(measure_latest and any(NO_PLAYS_IN_BIGQUERY in ln for ln in measure_latest["log_tail"])),
    }


def readme_row(report: dict[str, Any], file_name: str) -> str:
    def latest(job: str) -> str:
        exs = report["jobs"][job]["executions"]
        if not exs:
            return "no executions"
        e = exs[0]
        return f"{e['status']} {e['start'] or e['created'] or ''} ({e['duration_s']}s)"

    fc = report["bigquery"]["forecasts_by_run"]
    node = sum(int(r["node_rows"]) for r in fc)
    cluster = sum(int(r["cluster_rows"]) for r in fc)
    stab = report["row_count_stability"]
    stable = "n/a (first report)" if stab["stable"] is None else ("yes" if stab["stable"] else "NO: " + ", ".join(f"{k} {v['previous']}->{v['current']}" for k, v in stab["changed"].items()))
    rc = report["row_counts"]
    return (f"| [{file_name}]({file_name}) | {latest('taal-sense')} | {latest('taal-measure')} "
            f"| {report['jobs']['taal-sense']['green_streak']}/{report['jobs']['taal-measure']['green_streak']} "
            f"| {node}/{cluster} | {len(fc)} | {', '.join(report['as_of']['forecasts_as_of_values']) or '-'} "
            f"| {report['as_of']['sales_daily_max_date'] or '-'} | {rc['gaps']} | {rc['plays']} / {rc['play_outcomes']} | {stable} |\n")


def write_outputs(report: dict[str, Any], out_dir: Path, day: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{day}.json"
    i = 1
    while path.exists():  # a second run the same day never overwrites the first
        i += 1
        path = out_dir / f"{day}_{i}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    readme = out_dir / "README.md"
    if not readme.exists():
        readme.write_text(README_HEADER, encoding="utf-8")
    with readme.open("a", encoding="utf-8") as f:
        f.write(readme_row(report, path.name))
    return path


def live_clients() -> tuple[Fetch, Query]:  # pragma: no cover - network
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    from google.cloud import bigquery

    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    session = AuthorizedSession(creds)
    client = bigquery.Client(project=PROJECT, location=REGION)

    def fetch(method: str, url: str, body: dict[str, Any] | None) -> dict[str, Any]:
        r = session.request(method, url, json=body, timeout=60)
        r.raise_for_status()
        return r.json()

    def query(sql: str, tenant_id: str) -> tuple[list[dict[str, Any]], int]:
        cfg = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("tenant_id", "STRING", tenant_id)])
        job = client.query(sql, job_config=cfg)
        rows = [dict(r) for r in job.result()]
        return rows, int(job.total_bytes_billed or 0)

    return fetch, query


def main(argv: list[str] | None = None) -> int:
    from agents.gate.config import load_tenant

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--executions", type=int, default=3, help="last N executions per job (default 3)")
    ap.add_argument("--out-dir", default=str(ROOT / "eval" / "raw" / "nightly_runs"))
    args = ap.parse_args(argv)
    now = datetime.now(UTC)
    day = now.date().isoformat()
    out_dir = Path(args.out_dir)
    fetch, query = live_clients()
    report = build_report(fetch, query, load_tenant().tenant_id, args.executions,
                          now.isoformat(timespec="seconds").replace("+00:00", "Z"), previous_report(out_dir, day + "~"))
    path = write_outputs(report, out_dir, day)
    s, m = report["jobs"]["taal-sense"], report["jobs"]["taal-measure"]
    print(f"nightly report -> {path}: sense streak {s['green_streak']}, measure streak {m['green_streak']}, "
          f"rows stable={report['row_count_stability']['stable']}, as_of={report['as_of']['latest_forecasts_as_of']}, "
          f"sales_daily max={report['as_of']['sales_daily_max_date']}, bytes billed={report['bigquery']['bytes_billed']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
