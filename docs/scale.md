# Scale

Structure from DECISIONS §0.1 row 1 (scalability) and §18 (cost-minimal multi-agent framework).
Every number below is labelled measured or not measured, and traces to a raw output committed
under `eval/raw/`; see `eval/evaluation.md` for the full table and the commands that produced it.

## Measured throughput (21 Sep 2026)

| Stage | Throughput | Status |
|---|---|---|
| Sense job, full nightly run (300 SKUs, 16 nodes/outlets), local backend | 3.8s total (forecast 2.5s, gaps 0.15s, segments+substitutes 1.2s) | measured: `uv run python -m jobs.sense`, local compute against LocalStore (default everywhere except the deployed `taal-sense` job's own env; see below); `eval/raw/sense_throughput_2026-09-20.json` |
| Planner Agent, one gap, live Vertex | 70.5s (rerun, proposed) to 110.9s (plan, no_play after 2 iterations) | measured: `harness.sweep_live` against a live `TAAL_MODEL_BACKEND=vertex` server, real Gemini calls; `eval/raw/sweep_vertex_2026-09-20.txt` |
| Planner Agent fan-out, 50 gaps, Batch API | not measured | the Batch API fan-out in DECISIONS §18.3 is a documented design, not built -- nothing in this repo submits a Batch job |
| Customer Agent, one turn, live Vertex | 4.5-6.9s across 3 live calls | measured: same sweep run |
| Vision intake, one photo, live Vertex | 3.9s | measured: same sweep run (`POST /capture` with an uploaded image) |
| BigQuery `AI.FORECAST` (TimesFM), full run, all qualifying series | 22.74s, 73,400,320 bytes billed, 25,060 rows / 895 series | measured live against `amru-509214`/`asia-south1`, job `c6b5e3ab-0855-48a7-97b9-952d441c562d`; `eval/raw/bigquery_ai_forecast_2026-09-27/full_run_result.json`. Wired behind `TAAL_FORECAST_BACKEND=bigquery_timesfm` (`jobs/sense/forecast_bigquery.py`), default `local` everywhere except the `taal-sense` job's own env |
| BigQuery bytes scanned, `TAAL_BATCH_STORE=bigquery` write path (`BigQueryStore.write()`, `04_rolldown.sql`'s node rolldown) | not measured -- blocked | `amru-509214` has no billing account enabled; BigQuery's free tier rejects every DML statement (`DELETE`/`MERGE`/`UPDATE`), confirmed with a real 403 against an unrelated table, while `SELECT`/`INSERT` both work. Both the rolldown step and every `BigQueryStore.write()` call issue a `DELETE`, so this path could not be exercised end-to-end; `eval/raw/bigquery_billing_dml_2026-09-27/finding.json` |

**`bigquery.Client` construction exists in four places.** Naming each and the runtime path that reaches it:
- `jobs/sense/copy.py::generate_copy_bigquery` -- reachable from a running server: `POST /approve` calls it when `TAAL_MODEL_BACKEND=vertex`, to run `AI.GENERATE_TABLE` for offer copy, with a 6s timeout and a templated-copy fallback on any failure. No bytes-scanned figure was captured for this call (the query is small and parameterized, no temp table); `eval/raw/bigquery_arima_xreg_forecast_2026-09-23.json` and `tests/unit/test_copy.py`'s own header cover the real bugs found running it live, not a bytes/cost number.
- `jobs/measure/cost.py` -- a standalone CLI (`python -m jobs.measure`), not called by any running server path or by Sense; `eval/raw/cost_measurement_2026-09-23.json` has bytes-billed figures for the runs that were made.
- `jobs/sense/forecast_bigquery.py::forecast_bigquery` -- reachable from `jobs/sense/run.py` only when `TAAL_FORECAST_BACKEND=bigquery_timesfm` (the `taal-sense` job's own env, never the demo tenant's serving path). Verified live for the `02_forecast_timesfm.sql` half (above); the `04_rolldown.sql` half is blocked by the billing gap.
- `agents/gate/bigquery_store.py::BigQueryStore` -- verified against real BigQuery for `SELECT`/load-style operations (`eval/raw/bigquery_store_2026-09-24/summary.json`, `eval/raw/bigquery_full_load_2026-09-24/summary.json`), and wired into `jobs/sense/run.py`/`jobs/measure/run.py` behind `TAAL_BATCH_STORE=bigquery` (default `local`; the demo tenant's judge-mode serving path, `services/api/sandbox.py::store_for()`, still returns `LocalStore`/`OverlayStore` unconditionally and was never switched). Its `write()` method's own `DELETE`-then-load pattern is blocked by the billing gap above, so this path is unit-tested but not verified live end-to-end.

These are single-run numbers against the seeded demo tenant, not a load test; see
`eval/evaluation.md` for caveats (a live planner run is 1-2 samples, not a distribution).

## Extrapolation to a 20,000-SKU retailer

The **Large** profile in DECISIONS §18.5 sizes this directly: 20,000 SKUs, 500 nodes, 1M
customers, ~2,000 gaps a night after the Cost Governor's triage, ~20,000 conversations a month.
The architecture does not change shape -- the same nightly BigQuery job, the same Planner Agent,
the same Customer Agent -- only three things scale: (1) the Cloud Tasks queue depth for the
Planner fan-out, (2) BigQuery partition/cluster pruning on `sales_daily`, `forecasts`, `gaps`
(already partitioned by date/deadline_date and clustered by sku), and (3) the triage threshold
(`thresholds.min_rupees_at_stake_for_planner`) that keeps nightly Planner runs bounded to the
gaps worth planning. [estimate: the shape holds; the exact throughput numbers for 20,000 SKUs are
not measured -- no tenant that size has run through Taal]

## Tenant model

`tenant_id` is a required column on every table (see `docs/DATA_MODEL.md`); one deployment can
serve many shops behind the same Cloud Run services and the same BigQuery dataset, filtered by
`tenant_id` on every query. Fixed costs -- the nightly job invocation, monitoring, the Cloud Run
services' idle floor -- are shared across tenants rather than duplicated per tenant.

## The three-CSV ingestion contract

A new tenant onboards with three CSVs. The contract is executable: `data/ingest/contract.py`
defines the columns and types, and `python -m data.ingest` validates them, derives each batch's
`online_sellby_date` under the tenant's rule (`agents/gate/sellby.py`), writes the LocalStore
tenant (the same tables `data/generator` writes, mapped onto `data/bigquery/ddl/01_products.sql`,
`03_inventory_batches.sql`, `05_sales_daily.sql`) and runs Sense on it. Extra columns are ignored.
Every contract problem is reported with file, line and column before anything is written.

| File | Required columns | Blank cell allowed in |
|---|---|---|
| `products.csv` | `sku, name, category, pack_size, pack_weight_g, unit_cost, list_price, margin_floor_pct, shelf_life_days, is_food` | `pack_size`, `pack_weight_g`, `margin_floor_pct` (blank = the tenant config's floor for the category) |
| `inventory_batches.csv` | `batch_id, sku, node_id, qty_on_hand, expiry_date, received_at, source` (`online_sellby_date` is derived, never supplied) | `expiry_date` (a non-perishable lot), `received_at`, `source` |
| `sales.csv` | `date, sku, node_id, units, revenue, on_promo` (daily grain; repeated `(date, sku, node_id)` rows are summed) | `revenue` |

Two optional files sharpen the result:

- `nodes.csv` (`node_id, type, lead_time_days, cluster_id`, optional `lat, lng`; `type` is
  `dark_store` or `outlet`). Without it every node is treated as an online dark store in one
  cluster with a 3-day lead time (`--default-lead-time-days`), and the CLI says so. Outlets matter
  because the online sell-by rule applies only at nodes that sell online.
- `inbound.csv` (`po_id, sku, node_id, qty, eta`). Without it Sense sees no stock in flight, so
  `stockout_risk` is an upper bound.

Round-trip proof, `make ingest-roundtrip`: the seeded tenant exported to these files
(`python -m data.ingest.export`) and ingested again gives the same 550 grocery gaps, byte for byte,
and the same 134,400 forecast rows. Measured on the seeded synthetic tenant, recomputed from
`eval/raw/ingest_roundtrip_2026-09-27/summary.json`. The 5 apparel `assortment_gap` rows are
excluded because they come from stylist asks, which are outside this contract. A 2-sku worked
example lives in `data/samples/`, checked byte-for-byte against the generator by
`tests/unit/test_ingest.py`.

## Cost profiles (DECISIONS §18.5)

| Profile | Who | Footprint | Estimated monthly cost |
|---|---|---|---|
| **Micro** [estimate] | one shop, one node, <= 500 SKUs, <= 1,000 customers, ~2 plays/day | shared multi-tenant deployment; Firestore-only serving; BigQuery in the free tier; on-device first-pass vision; no Looker | Gemini ~ Rs 150-300; everything else inside free tiers -> **~ Rs 200-500** |
| **Mid** (the demo persona) [estimate] | 300 SKUs, 10 nodes, 6 outlets, ~4,000 customers, ~30 plays/night, ~500 conversations/month | same deployment; BigQuery a few GB; Cloud Run scale-to-zero; Looker Studio (free) | Planner ~ Rs 900-2,000; conversations ~ Rs 700; BigQuery ~ Rs 400-1,600; Cloud Run/Firestore ~ Rs 0-800 -> **~ Rs 2,500-5,000** |
| **Large** [estimate] | 20,000 SKUs, 500 nodes, 1M customers, ~2,000 gaps/night after triage, ~20,000 conversations/month | dedicated project; Cloud Tasks fan-out; batch Planner; partitioned BigQuery; still scale-to-zero serving | Planner ~ Rs 60,000-150,000 (batch + caching, triaged); conversations ~ Rs 26,000; BigQuery ~ Rs 8,000-25,000; Cloud Run ~ Rs 4,000-8,000 -> **~ Rs 1-2 lakh**, against rupees at stake in the crores |

All three profiles run the same code with a tenant config; the difference is triage thresholds,
budget caps, and whether Looker Studio is attached (DECISIONS §18.5). Every rupee figure in this
table is an estimate from list prices, not a measurement; the build replaces them with the real
numbers from the billing export (`cost_per_play`, `cost_as_pct_of_rupees_at_stake`) once a tenant
has run for a full billing cycle.

## What breaks first

1. **The Planner fan-out queue**, past a few thousand gaps a night, if the Cost Governor's
   triage threshold is set too low for the tenant's SKU count -- the nightly job window (hours,
   not minutes) becomes the binding constraint before BigQuery compute does.
2. **The local seasonal-xreg re-forecast** (`jobs/sense/forecast.py`, called in process from
   `services/api/approve.py`), if the number of concurrent Approve actions during a demo or a
   promotion launch exceeds what this call can serve inside the 15 s budget -- this is a
   per-series call, so it scales with concurrent approvals, not tenant size. BigQuery `ML.FORECAST`
   on `ARIMA_PLUS_XREG` was verified separately (`eval/raw/bigquery_arima_xreg_forecast_2026-09-23.json`)
   and is not on this path.
3. **Conversation volume**, since it is the only per-customer LLM cost with no batch discount
   (chat is live, not nightly); the per-play conversation budget the Cost Governor sets exists
   specifically to cap this before it becomes the dominant cost line.
4. **BigQuery bytes scanned**, if partition/cluster pruning is bypassed by a query that filters
   on a column other than the partition/cluster key (e.g. scanning all of `sales_daily` by
   `node_id` instead of `date`+`sku`) -- the assertions and Sense scripts in this repo always
   filter on `tenant_id` plus the partition column first for this reason.
5. **Firestore document contention** on a single `stock/{node}/{sku}` document -- a risk only if
   the optional Firestore serving cache is turned on (`TAAL_SERVING_CACHE=firestore`; `infra/deploy.sh`
   sets it only when a maintainer flips `ENABLE_SERVING_CACHE` from its hard-coded default of 0,
   `infra/deploy.sh:22`, so it is off in the deployed service today); many concurrent judge-mode visitors
   reading the same seeded tenant are isolated today by the per-visitor namespace clone in
   DECISIONS §5.6 instead.
