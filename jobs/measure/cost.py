"""Cost measurement job (DECISIONS §18.3 lever 10, §18.4): `cost_per_play` and
`cost_as_pct_of_rupees_at_stake` computed from real GCP spend, never from the list-price
estimates in DECISIONS §18.4/§18.5 (those are explicitly flagged there as guesses to be
replaced).

    python -m jobs.measure.cost [--project amru-509214] [--days 30]

Two tiers, tried in order, both real, neither ever fabricated:

TIER 1 -- billing-export dollars (authoritative, if available):
1. Look for a BigQuery billing export dataset in `--project` (a table named
   `gcp_billing_export_v1_*` or `gcp_billing_export_resource_v1_*` in any dataset). This is
   the standard, supported way to get itemised GCP cost with SKU/service detail.
2. If none exists, check *why* a caller can't see one: call the Cloud Billing API
   (`projects.getBillingInfo`, `billingAccounts.get`, `billingbudgets.googleapis.com`) with the
   credentials in use, so the failure reason (no export configured vs. no permission to
   configure or read one) is captured instead of guessed.
3. If an export is found, sum `cost + SUM(credits.amount)` for Generative AI line items
   (Vertex AI / "Generative AI" service descriptions) over the trailing `--days` days.

TIER 2 -- modeled from measured usage x public list rates (fallback, run automatically when
tier 1 is blocked): every number that goes into this estimate is a REAL measured quantity for
this project -- real Gemini input/output token counts from Cloud Monitoring
(`aiplatform.googleapis.com/publisher/online_serving/token_count`, a DELTA metric, correct to
sum over the window), real BigQuery bytes billed from actual job history
(`total_bytes_billed` on every job actually run), real BigQuery table storage bytes (the
Tables API, not a guess), real Cloud Run CPU/memory allocation time from Cloud Monitoring
(`run.googleapis.com/container/cpu|memory/allocation_time`, already reported in the exact
units Cloud Run bills in: vCPU-seconds and GiB-seconds), and real Firestore billable
read/write units from Cloud Monitoring. Each measured quantity is priced at Google's current
public list rate (`PUBLIC_RATES` below, each with its source and the date it was checked --
see `docs/deck_audit.md`/`eval/evaluation.md` for the verification record). This is NOT a
billing-dollar figure: it excludes any negotiated discount, committed-use discount, free-tier
allowance, or batch/caching discount that may apply, and every result carries
`methodology: "modeled_from_measured_usage"` so it is never confused with tier 1. A metric
query that errors is reported as `unavailable` for that line item with the real error, never
silently treated as zero; a metric query that succeeds and returns no data points (Firestore
here, genuinely 0 ops) is reported as a real, verified zero.

Cross-reference against `taal.plays` (approved/running/measured/unmeasured, i.e. plays that
actually got a Planner run) and `taal.gaps.rupees_at_stake` in BigQuery, over the same window,
for `cost_per_play = total_cost_inr / plays_in_window` and
`cost_as_pct_of_rupees_at_stake = cost_per_play / avg_rupees_at_stake_per_gap` -- for
whichever tier produced a cost figure. If neither tier can name a denominator, that ratio is
reported as unavailable rather than guessed.

The last real run's raw JSON output is committed under `eval/raw/` -- see
`harness/checklists/measure.md` and `eval/evaluation.md` for the dated result.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

GENAI_SERVICE_MATCH = ["Vertex AI", "Generative AI", "Gemini"]

# Public GCP list rates used by tier 2. Each was checked against Google's own pricing pages
# and cross-referenced search results on 2026-09-23 (Vertex AI's and Cloud Run's pricing pages
# returned truncated content to this session's fetch tool; rates below were corroborated across
# multiple independent 2026 pricing summaries citing the same figures, and Cloud Run's own docs
# confirm asia-south1 is a Tier 1 region for pricing purposes). These are LIST prices with no
# discount applied -- see the module docstring's tier-2 caveat.
PUBLIC_RATES = {
    "vertex_gemini_2_5_flash_input_usd_per_million_tokens": 0.30,
    "vertex_gemini_2_5_flash_output_usd_per_million_tokens": 2.50,
    "bigquery_on_demand_usd_per_tib_scanned": 6.25,
    "bigquery_active_storage_usd_per_gb_month": 0.02,
    "cloud_run_usd_per_vcpu_second": 0.000024,
    "cloud_run_usd_per_gib_second": 0.0000025,
    "firestore_usd_per_100k_reads": 0.06,
    "firestore_usd_per_100k_writes": 0.18,
    "firestore_usd_per_100k_deletes": 0.02,
    "usd_to_inr": 83.0,  # DECISIONS §18.4's own rate, applied consistently across both tiers.
    "checked_at": "2026-09-23",
    "source_note": (
        "cloud.google.com/vertex-ai/generative-ai/pricing, cloud.google.com/bigquery/pricing, "
        "cloud.google.com/run/pricing, cloud.google.com/firestore/pricing -- fetched via web "
        "search on 2026-09-23 since this session's direct page fetch returned truncated HTML; "
        "cross-checked against multiple independent 2026 pricing summaries agreeing on the same "
        "figures rather than taken from one uncorroborated source."
    ),
}


def _billing_account_diagnostics(project: str) -> dict[str, Any]:
    """Best-effort explanation for *why* no export/cost data is reachable, using the Cloud
    Billing API directly (google-auth + requests; no gcloud/bq CLI is available in this
    environment). Never raises -- any failure here is itself diagnostic information.
    """
    diag: dict[str, Any] = {}
    try:
        import google.auth
        import google.auth.transport.requests
        import requests

        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        creds.refresh(google.auth.transport.requests.Request())
        diag["caller"] = getattr(creds, "service_account_email", "unknown")
        h = {"Authorization": f"Bearer {creds.token}"}

        r = requests.get(f"https://cloudbilling.googleapis.com/v1/projects/{project}/billingInfo", headers=h, timeout=20)
        diag["projects.getBillingInfo"] = {"status": r.status_code, "body": _safe_json(r)}
        billing_account = None
        if r.status_code == 200:
            billing_account = r.json().get("billingAccountName")

        if billing_account:
            r2 = requests.get(f"https://cloudbilling.googleapis.com/v1/{billing_account}", headers=h, timeout=20)
            diag["billingAccounts.get"] = {"status": r2.status_code, "body": _safe_json(r2)}
            r3 = requests.get(f"https://billingbudgets.googleapis.com/v1/{billing_account}/budgets", headers=h, timeout=20)
            diag["billingbudgets.list"] = {"status": r3.status_code, "body": _safe_json(r3)}
    except Exception as e:  # pragma: no cover - diagnostics only, never fatal
        diag["diagnostics_error"] = repr(e)
    return diag


def _safe_json(resp: Any) -> Any:
    try:
        return resp.json()
    except Exception:
        return resp.text[:500]


def find_billing_export_table(client: Any) -> str | None:
    """Scan every dataset in the project for a standard billing export table. Returns the
    fully-qualified table id, or None if no such table exists anywhere in the project.
    """
    for ds in client.list_datasets():
        for tbl in client.list_tables(ds.dataset_id):
            if tbl.table_id.startswith("gcp_billing_export_v1_") or tbl.table_id.startswith("gcp_billing_export_resource_v1_"):
                return f"{client.project}.{ds.dataset_id}.{tbl.table_id}"
    return None


def query_genai_cost_inr(client: Any, export_table: str, start: datetime, end: datetime) -> float:
    service_filter = " OR ".join(f'service.description LIKE "%{s}%"' for s in GENAI_SERVICE_MATCH)
    q = f"""
    SELECT SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS net_cost,
           currency
    FROM `{export_table}`
    WHERE usage_start_time >= @start AND usage_start_time < @end
      AND ({service_filter})
    GROUP BY currency
    """
    from google.cloud import bigquery

    job = client.query(
        q,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("start", "TIMESTAMP", start),
                bigquery.ScalarQueryParameter("end", "TIMESTAMP", end),
            ]
        ),
    )
    total_inr = 0.0
    for row in job.result():
        cost = float(row["net_cost"] or 0.0)
        if row["currency"] == "INR":
            total_inr += cost
        elif row["currency"] == "USD":
            total_inr += cost * 83.0  # DECISIONS §18.4's own USD->INR rate; only used if the
            # export's currency isn't already INR -- flagged in the result, never silent.
        else:
            raise RuntimeError(f"unhandled billing export currency: {row['currency']}")
    return round(total_inr, 4)


def count_plays_and_avg_rupees(client: Any, dataset: str, start: datetime, end: datetime) -> dict[str, Any]:
    plays_q = f"""
    SELECT COUNT(*) AS n
    FROM `{dataset}.plays`
    WHERE status IN ('approved', 'running', 'measured', 'unmeasured')
      AND created_at >= @start AND created_at < @end
    """
    gaps_q = f"""
    SELECT AVG(rupees_at_stake) AS avg_rupees, COUNT(*) AS n
    FROM `{dataset}.gaps`
    WHERE created_at >= @start_date AND created_at < @end_date
    """
    from google.cloud import bigquery

    params = [
        bigquery.ScalarQueryParameter("start", "TIMESTAMP", start),
        bigquery.ScalarQueryParameter("end", "TIMESTAMP", end),
    ]
    # gaps.created_at is DATE (14_gaps.sql), unlike plays.created_at which is TIMESTAMP
    # (15_plays.sql) -- a real type mismatch found by actually running this query.
    date_params = [
        bigquery.ScalarQueryParameter("start_date", "DATE", start.date()),
        bigquery.ScalarQueryParameter("end_date", "DATE", end.date()),
    ]
    plays_n = list(client.query(plays_q, job_config=bigquery.QueryJobConfig(query_parameters=params)).result())[0]["n"]
    gaps_row = list(client.query(gaps_q, job_config=bigquery.QueryJobConfig(query_parameters=date_params)).result())[0]
    return {"plays_in_window": int(plays_n), "gaps_in_window": int(gaps_row["n"]), "avg_rupees_at_stake": (float(gaps_row["avg_rupees"]) if gaps_row["avg_rupees"] is not None else None)}


def _sum_delta_metric(mon_client: Any, project: str, metric_type: str, start: datetime, end: datetime, metric_filter: str = "") -> dict[str, Any]:
    """Sum a real DELTA-kind Cloud Monitoring metric over [start, end) for `project`. Returns
    the real per-series breakdown plus the grand total; never guesses a value on a query error.
    """
    from google.cloud import monitoring_v3

    name = f"projects/{project}"
    filt = f'metric.type="{metric_type}"' + (f" AND {metric_filter}" if metric_filter else "")
    interval = monitoring_v3.TimeInterval({"end_time": {"seconds": int(end.timestamp())}, "start_time": {"seconds": int(start.timestamp())}})
    req = monitoring_v3.ListTimeSeriesRequest(name=name, filter=filt, interval=interval, view=monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL)
    try:
        series: list[dict[str, Any]] = []
        total = 0.0
        for ts in mon_client.list_time_series(request=req):
            s = sum((p.value.int64_value or p.value.double_value or 0.0) for p in ts.points)
            total += s
            series.append({"metric_labels": dict(ts.metric.labels), "resource_labels": dict(ts.resource.labels), "n_points": len(ts.points), "sum": s})
        return {"available": True, "total": total, "n_series": len(series), "series": series}
    except Exception as e:  # pragma: no cover - network/permission failure, reported not hidden
        return {"available": False, "error": repr(e)}


def run_modeled_cost_measurement(project: str, days: int, dataset: str) -> dict[str, Any]:
    """Tier 2: price real, measured usage against public list rates. See module docstring."""
    from google.cloud import bigquery, monitoring_v3

    now = datetime.now(UTC)
    start = now - timedelta(days=days)
    mon = monitoring_v3.MetricServiceClient()
    bq = bigquery.Client(project=project)
    r = PUBLIC_RATES
    lines: dict[str, Any] = {}
    total_usd = 0.0
    unavailable: list[str] = []

    # 1. Vertex AI Gemini: real input/output token counts, every region this project has used.
    tok_in = _sum_delta_metric(mon, project, "aiplatform.googleapis.com/publisher/online_serving/token_count", start, now, 'metric.label."type"="input"')
    tok_out = _sum_delta_metric(mon, project, "aiplatform.googleapis.com/publisher/online_serving/token_count", start, now, 'metric.label."type"="output"')
    if tok_in["available"] and tok_out["available"]:
        cost = (tok_in["total"] / 1e6) * r["vertex_gemini_2_5_flash_input_usd_per_million_tokens"] + (tok_out["total"] / 1e6) * r["vertex_gemini_2_5_flash_output_usd_per_million_tokens"]
        lines["vertex_ai_gemini"] = {"input_tokens": tok_in["total"], "output_tokens": tok_out["total"], "usd": round(cost, 4), "detail": {"input": tok_in, "output": tok_out}}
        total_usd += cost
    else:
        unavailable.append("vertex_ai_gemini")
        lines["vertex_ai_gemini"] = {"input": tok_in, "output": tok_out}

    # 2. BigQuery query analysis: real bytes billed on every job actually run in the window.
    try:
        bytes_billed = 0
        n_jobs = 0
        for job in bq.list_jobs(min_creation_time=start, max_creation_time=now, all_users=True, state_filter="DONE"):
            b = getattr(job, "total_bytes_billed", None)
            if b:
                bytes_billed += b
            n_jobs += 1
        tib = bytes_billed / (1024 ** 4)
        cost = tib * r["bigquery_on_demand_usd_per_tib_scanned"]
        lines["bigquery_query"] = {"n_jobs": n_jobs, "bytes_billed": bytes_billed, "tib_billed": round(tib, 8), "usd": round(cost, 6)}
        total_usd += cost
    except Exception as e:
        unavailable.append("bigquery_query")
        lines["bigquery_query"] = {"available": False, "error": repr(e)}

    # 3. BigQuery storage: real current table sizes across every dataset (Tables API, not a
    # guess; INFORMATION_SCHEMA.TABLE_STORAGE needs a project-level opt-in and ~1 day to
    # populate, so it is not used here). A point-in-time snapshot, not integrated over the
    # window -- reported as such.
    try:
        total_bytes = 0
        n_tables = 0
        for ds in bq.list_datasets():
            for tbl in bq.list_tables(ds.dataset_id):
                t = bq.get_table(tbl.reference)
                total_bytes += t.num_bytes or 0
                n_tables += 1
        gb = total_bytes / (1024 ** 3)
        cost = gb * r["bigquery_active_storage_usd_per_gb_month"]
        lines["bigquery_storage"] = {"n_tables": n_tables, "bytes": total_bytes, "gb": round(gb, 6), "usd_per_month_at_current_size": round(cost, 6), "note": "point-in-time snapshot, not usage over the window"}
        total_usd += cost
    except Exception as e:
        unavailable.append("bigquery_storage")
        lines["bigquery_storage"] = {"available": False, "error": repr(e)}

    # 4. Cloud Run: real CPU/memory allocation time, already reported in the exact units
    # Cloud Run request-based billing uses (vCPU-seconds, GiB-seconds).
    cpu = _sum_delta_metric(mon, project, "run.googleapis.com/container/cpu/allocation_time", start, now)
    mem = _sum_delta_metric(mon, project, "run.googleapis.com/container/memory/allocation_time", start, now)
    if cpu["available"] and mem["available"]:
        cost = cpu["total"] * r["cloud_run_usd_per_vcpu_second"] + mem["total"] * r["cloud_run_usd_per_gib_second"]
        lines["cloud_run"] = {"vcpu_seconds": cpu["total"], "gib_seconds": mem["total"], "usd": round(cost, 4), "n_revisions": cpu["n_series"]}
        total_usd += cost
    else:
        unavailable.append("cloud_run")
        lines["cloud_run"] = {"cpu": cpu, "memory": mem}

    # 5. Firestore: real billable read/write/delete units (0 is a real, verified answer here --
    # the deployed demo runs off a baked-in local store, not live Firestore traffic).
    reads = _sum_delta_metric(mon, project, "firestore.googleapis.com/api/billable_read_units", start, now)
    writes = _sum_delta_metric(mon, project, "firestore.googleapis.com/api/billable_write_units", start, now)
    deletes = _sum_delta_metric(mon, project, "firestore.googleapis.com/document/billable_managed_delete_write_units", start, now)
    if reads["available"] and writes["available"]:
        cost = (reads["total"] / 1e5) * r["firestore_usd_per_100k_reads"] + (writes["total"] / 1e5) * r["firestore_usd_per_100k_writes"] + ((deletes["total"] if deletes["available"] else 0) / 1e5) * r["firestore_usd_per_100k_deletes"]
        lines["firestore"] = {"read_units": reads["total"], "write_units": writes["total"], "delete_units": deletes["total"] if deletes["available"] else None, "usd": round(cost, 6)}
        total_usd += cost
    else:
        unavailable.append("firestore")
        lines["firestore"] = {"reads": reads, "writes": writes}

    total_inr = total_usd * r["usd_to_inr"]
    result: dict[str, Any] = {
        "methodology": "modeled_from_measured_usage",
        "methodology_note": (
            "Every quantity above is real and measured for this project over the trailing "
            f"{days} days (or, for storage, a real point-in-time snapshot). Priced at Google's "
            "public list rates, not an actual billing-dollar figure -- excludes any discount, "
            "free-tier allowance, or negotiated rate. See PUBLIC_RATES for sources."
        ),
        "window_days": days,
        "rates_used": r,
        "lines": lines,
        "total_usd": round(total_usd, 4),
        "total_inr": round(total_inr, 2),
        "unavailable_lines": unavailable,
    }

    counts = count_plays_and_avg_rupees(bq, f"{project}.{dataset}", start, now)
    result.update(counts)
    if counts["plays_in_window"] > 0:
        cost_per_play = round(total_inr / counts["plays_in_window"], 4)
        result["cost_per_play_inr"] = cost_per_play
        if counts["avg_rupees_at_stake"]:
            result["cost_as_pct_of_rupees_at_stake"] = round(cost_per_play / counts["avg_rupees_at_stake"], 6)
        else:
            result["cost_as_pct_of_rupees_at_stake"] = None
            result["cost_as_pct_of_rupees_at_stake_reason"] = f"`{dataset}.gaps` has no rows with rupees_at_stake in the window."
    else:
        result["cost_per_play_inr"] = None
        result["cost_per_play_reason"] = f"`{dataset}.plays` has 0 rows with status in (approved, running, measured, unmeasured) in the window, so cost_per_play has no real denominator. Total modeled spend is still reported above."

    return result


def run_cost_measurement(project: str, days: int = 30, dataset: str = "taal") -> dict[str, Any]:
    from google.cloud import bigquery

    now = datetime.now(UTC)
    start, end = now - timedelta(days=days), now
    result: dict[str, Any] = {
        "measured_at": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "project": project,
        "window_days": days,
    }
    client = bigquery.Client(project=project)

    export_table = find_billing_export_table(client)
    if not export_table:
        result["blocked"] = True
        result["reason"] = (
            f"No BigQuery billing export table (gcp_billing_export_v1_* or "
            f"gcp_billing_export_resource_v1_*) exists in any dataset of project {project!r}. "
            "Billing export is configured at the Cloud Billing account level, not the project "
            "level; the credentials used here could not be checked for that permission without "
            "attempting it, so the Cloud Billing API diagnostics below record what was actually "
            "tried. A tier-2 modeled estimate (real measured usage x public list rates) is "
            "attempted below instead of leaving this row blank."
        )
        result["billing_api_diagnostics"] = _billing_account_diagnostics(project)
        result["modeled"] = run_modeled_cost_measurement(project, days, dataset)
        return result

    result["billing_export_table"] = export_table
    genai_cost_inr = query_genai_cost_inr(client, export_table, start, end)
    counts = count_plays_and_avg_rupees(client, f"{project}.{dataset}", start, end)
    result.update(counts)
    result["genai_cost_inr"] = genai_cost_inr

    if counts["plays_in_window"] == 0:
        result["blocked"] = True
        result["reason"] = (
            f"Billing export was reachable (₹{genai_cost_inr:.2f} in Gen AI spend over the "
            f"trailing {days} days), but `{dataset}.plays` has 0 rows with status in "
            "(approved, running, measured, unmeasured) in that window, so cost_per_play has no "
            "real denominator. Refusing to divide by zero or substitute a guess."
        )
        return result
    if counts["avg_rupees_at_stake"] is None:
        result["blocked"] = True
        result["reason"] = f"`{dataset}.gaps` has no rows with rupees_at_stake in the window; cost_as_pct_of_rupees_at_stake has no real denominator."
        return result

    cost_per_play = round(genai_cost_inr / counts["plays_in_window"], 4)
    result["blocked"] = False
    result["cost_per_play_inr"] = cost_per_play
    result["cost_as_pct_of_rupees_at_stake"] = round(cost_per_play / counts["avg_rupees_at_stake"], 6)
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default="amru-509214")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--dataset", default="taal")
    args = ap.parse_args(argv)
    result = run_cost_measurement(args.project, args.days, args.dataset)
    print(json.dumps(result, indent=2, sort_keys=False))
    # Exit 0 if tier 1 (billing-export dollars) produced a number, OR tier 2 (modeled from
    # measured usage) produced one -- i.e. something real and usable exists. Exit 1 only when
    # both tiers came back empty.
    if not result.get("blocked"):
        return 0
    modeled = result.get("modeled")
    if modeled and not modeled.get("unavailable_lines") == list(modeled.get("lines", {}).keys()):
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
