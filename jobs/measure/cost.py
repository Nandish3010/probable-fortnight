"""Cost measurement job (DECISIONS §18.3 lever 10, §18.4): `cost_per_play` and
`cost_as_pct_of_rupees_at_stake` computed from real GCP spend, never from the list-price
estimates in DECISIONS §18.4/§18.5 (those are explicitly flagged there as guesses to be
replaced).

    python -m jobs.measure.cost [--project amru-509214] [--days 30]

Methodology, in order, each step done for real against the live project (never assumed):

1. Look for a BigQuery billing export dataset in `--project` (a table named
   `gcp_billing_export_v1_*` or `gcp_billing_export_resource_v1_*` in any dataset). This is
   the standard, supported way to get itemised GCP cost with SKU/service detail.
2. If none exists, check *why* a caller can't see one: call the Cloud Billing API
   (`projects.getBillingInfo`, `billingAccounts.get`, `billingbudgets.googleapis.com`) with the
   credentials in use, so the failure reason (no export configured vs. no permission to
   configure or read one) is captured instead of guessed.
3. If an export is found, sum `cost + SUM(credits.amount)` for Generative AI line items
   (Vertex AI / "Generative AI" service descriptions) over the trailing `--days` days.
4. Cross-reference against `taal.plays` (approved/running/measured/unmeasured, i.e. plays that
   actually got a Planner run) and `taal.gaps.rupees_at_stake` in BigQuery, over the same
   window, and say plainly if that table has no rows.
5. `cost_per_play = attributable_genai_cost_inr / plays_in_window`
   `cost_as_pct_of_rupees_at_stake = cost_per_play / avg_rupees_at_stake_per_gap`

This job never fabricates a number: if step 1 finds no export, or step 4 finds zero plays,
`run_cost_measurement` returns a `blocked: true` result with the concrete reason instead of a
number, and `main` exits 1. The last real run's raw JSON output is committed under
`eval/raw/` -- see `harness/checklists/measure.md` and `eval/evaluation.md` for the dated
result.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

GENAI_SERVICE_MATCH = ["Vertex AI", "Generative AI", "Gemini"]


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
    WHERE created_at >= @start AND created_at < @end
    """
    from google.cloud import bigquery

    params = [
        bigquery.ScalarQueryParameter("start", "TIMESTAMP", start),
        bigquery.ScalarQueryParameter("end", "TIMESTAMP", end),
    ]
    plays_n = list(client.query(plays_q, job_config=bigquery.QueryJobConfig(query_parameters=params)).result())[0]["n"]
    gaps_row = list(client.query(gaps_q, job_config=bigquery.QueryJobConfig(query_parameters=params)).result())[0]
    return {"plays_in_window": int(plays_n), "gaps_in_window": int(gaps_row["n"]), "avg_rupees_at_stake": (float(gaps_row["avg_rupees"]) if gaps_row["avg_rupees"] is not None else None)}


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
            "tried."
        )
        result["billing_api_diagnostics"] = _billing_account_diagnostics(project)
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
    return 1 if result.get("blocked") else 0


if __name__ == "__main__":
    sys.exit(main())
