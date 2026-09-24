# Scale

Structure from DECISIONS §0.1 row 1 (scalability) and §18 (cost-minimal multi-agent framework).
Every number below is labelled measured or not measured, and traces to a raw output committed
under `eval/raw/`; see `eval/evaluation.md` for the full table and the commands that produced it.

## Measured throughput (21 Sep 2026)

| Stage | Throughput | Status |
|---|---|---|
| Sense job, full nightly run (300 SKUs, 16 nodes/outlets) | 3.8s total (forecast 2.5s, gaps 0.15s, segments+substitutes 1.2s) | measured: `uv run python -m jobs.sense`, local compute against LocalStore -- not a BigQuery job (see below); `eval/raw/sense_throughput_2026-09-20.json` |
| Planner Agent, one gap, live Vertex | 70.5s (rerun, proposed) to 110.9s (plan, no_play after 2 iterations) | measured: `harness.sweep_live` against a live `TAAL_MODEL_BACKEND=vertex` server, real Gemini calls; `eval/raw/sweep_vertex_2026-09-20.txt` |
| Planner Agent fan-out, 50 gaps, Batch API | not measured | the Batch API fan-out in DECISIONS §18.3 is a documented design, not built -- nothing in this repo submits a Batch job |
| Customer Agent, one turn, live Vertex | 4.5-6.9s across 3 live calls | measured: same sweep run |
| Vision intake, one photo, live Vertex | 3.9s | measured: same sweep run (`POST /capture` with an uploaded image) |
| BigQuery bytes scanned, one Sense run | not measured | Sense's forecasting still reads and writes LocalStore, not BigQuery -- `jobs/sense/forecast.py` (the path `jobs/sense/run.py` actually calls) has no `bigquery.Client` construction, so there is no bytes-scanned figure for the Sense job itself |

**Correction: `bigquery.Client` construction exists in three places**, none of them in Sense's forecasting path above. Naming each and the runtime path that reaches it:
- `jobs/sense/copy.py::generate_copy_bigquery` -- reachable from a running server: `POST /approve` calls it when `TAAL_MODEL_BACKEND=vertex`, to run `AI.GENERATE_TABLE` for offer copy, with a 6s timeout and a templated-copy fallback on any failure. No bytes-scanned figure was captured for this call (the query is small and parameterized, no temp table); `eval/raw/bigquery_arima_xreg_forecast_2026-09-23.json` and `tests/unit/test_copy.py`'s own header cover the real bugs found running it live, not a bytes/cost number.
- `jobs/measure/cost.py` -- a standalone CLI (`python -m jobs.measure`), not called by any running server path or by Sense; `eval/raw/cost_measurement_2026-09-23.json` has bytes-billed figures for the runs that were made.
- `agents/gate/bigquery_store.py::BigQueryStore` -- verified against real BigQuery (`eval/raw/bigquery_store_2026-09-24/summary.json`, `eval/raw/bigquery_full_load_2026-09-24/summary.json`) but **not wired into any runtime path**: `services/api/sandbox.py::store_for()` still returns `LocalStore`/`OverlayStore` unconditionally, so no bytes-scanned figure applies to a live request.

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

A new tenant onboards by providing three CSVs matching the columns below (a superset maps
straight onto the DDL in `data/bigquery/ddl/01_products.sql`, `03_inventory_batches.sql`,
`05_sales_daily.sql`; extra columns are ignored, missing required ones fail validation before any
BigQuery load):

| File | Required columns |
|---|---|
| `products.csv` | `sku, name, category, pack_size, pack_weight_g, unit_cost, list_price, margin_floor_pct, shelf_life_days, is_food` |
| `inventory_batches.csv` | `batch_id, sku, node_id, qty_on_hand, expiry_date, received_at, source` (`online_sellby_date` is derived, not supplied) |
| `sales_daily.csv` | `date, sku, node_id, units, revenue, on_promo` |

`nodes.csv` (node_id, type, lat, lng, lead_time_days, cluster_id) is required alongside these
three in practice -- gaps cannot be computed without node cluster assignment -- but the "three-CSV
contract" language in DECISIONS §18 refers to the demand-side minimum; a tenant with one node can
supply a one-row `nodes.csv` and skip the cluster-rolldown step entirely.

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
2. **`ML.FORECAST` at the single-series re-forecast path**, if the number of concurrent Approve
   actions during a demo or a promotion launch exceeds what a single pre-trained model call can
   serve inside the 15 s budget -- this is a per-series call, so it scales with concurrent
   approvals, not tenant size.
3. **Conversation volume**, since it is the only per-customer LLM cost with no batch discount
   (chat is live, not nightly); the per-play conversation budget the Cost Governor sets exists
   specifically to cap this before it becomes the dominant cost line.
4. **BigQuery bytes scanned**, if partition/cluster pruning is bypassed by a query that filters
   on a column other than the partition/cluster key (e.g. scanning all of `sales_daily` by
   `node_id` instead of `date`+`sku`) -- the assertions and Sense scripts in this repo always
   filter on `tenant_id` plus the partition column first for this reason.
5. **Firestore document contention** on a single `stock/{node}/{sku}` document during a demo
   with many concurrent judge-mode visitors reading the same seeded tenant -- mitigated by the
   per-visitor namespace clone in DECISIONS §5.6, not by this layer.
