# Data model

Every table under `data/bigquery/ddl/*.sql`, dataset `taal`. Column names here are the contract;
if a name in this file and the DDL ever disagree, the DDL wins and this file is stale.

## Tables

### `products` (01)
- `tenant_id` -- which tenant this row belongs to
- `sku` -- product key
- `name` -- display name
- `category` -- category key (drives margin floor, festival matching, substitute search)
- `pack_size` -- human pack size string
- `pack_weight_g` -- grams per unit; input to the waste-kg estimate in Measure
- `unit_cost` -- rupees; basis of every write-off rupee figure
- `list_price` -- rupees; basis of stockout's lost-margin figure
- `margin_floor_pct` -- category margin floor, read by the gate
- `shelf_life_days` -- input to the online sell-by calculation
- `is_food` -- gates the sell-by rule; non-food uses expiry as its own sell-by

### `nodes` (02)
- `tenant_id`, `node_id` -- key
- `name` -- display name
- `type` -- `dark_store` (online-fulfilling) or `outlet` (physical only); gates online_sellby_breach
- `lat`, `lng` -- coordinates (used for `node_radius_km` audience filters)
- `lead_time_days` -- input to stockout_risk
- `cluster_id` -- forecast grain; nodes in a cluster share a TimesFM/ARIMA_PLUS_XREG series

### `inventory_batches` (03)
- `tenant_id`, `batch_id` -- key
- `sku`, `node_id` -- location
- `qty_on_hand` -- units in this lot
- `expiry_date` -- physical expiry
- `online_sellby_date` -- derived by `agents/gate/sellby.py`, see below
- `received_at` -- when the lot arrived
- `source` -- `system` or `photo`
- `capture_ref` -- Cloud Storage ref, set only for photo-captured rows
- `sellby_rule_version` -- which `sellby_rule` version computed `online_sellby_date` for this row

### `inbound` (04)
- `tenant_id`, `po_id` -- key; `sku`, `node_id` -- what and where; `qty` -- units; `eta` -- arrival date

### `sales_daily` (05)
- `tenant_id`, `date`, `sku`, `node_id` -- grain
- `units` -- units sold that day
- `revenue` -- rupees that day
- `on_promo` -- whether a promotion was live; feeds the forecast's promo coefficient

### `future_regressors` (06)
- `tenant_id`, `date`, `sku`, `cluster_id` -- grain (cluster-level, matches the forecast model's id_cols)
- `on_promo` -- set by an approved play's window
- `is_festival` -- set from `festival_calendar`
- `festival_name` -- which festival, if any
- `play_id` -- which play set `on_promo`, if any

### `orders` (07) / `order_lines` (08)
- `orders`: `tenant_id`, `order_id`, `customer_id`, `node_id`, `channel`, `ts`, `total_inr`
- `order_lines`: `tenant_id`, `order_id`, `line_no`, `customer_id`, `node_id`, `sku`, `qty`,
  `price` (unit list price at order time), `discount` (rupees off per unit), `play_id` (links the
  line to the play that produced it; Measure joins on this), `ts`

### `customers` (09)
- `tenant_id`, `customer_id` -- key
- `display_name`, `home_node_id`, `language` (`en`/`kn`) -- profile
- `rfm_tier` -- recency/frequency/monetary tier label
- `segment_id` -- KMEANS cluster, written by `06_segments.sql`
- `subscription_skus` -- active subscriptions; the gate excludes these from discount plays on the same sku
- `created_at`

### `affinity` (10)
- `tenant_id`, `customer_id`, `sku`, `score` -- co-purchase affinity in [0, 1]; feeds audience `mean_affinity`

### `segments` (11)
- `tenant_id`, `segment_id`, `name` (human-written), `k` (=6), `features` (recency/frequency/monetary/top_category)

### `consent` (12)
- `tenant_id`, `customer_id`, `channel`, `purpose`, `source`, `ts`, `withdrawn_at` -- see the
  consent-native design note below

### `forecasts` (13)
- `tenant_id`, `run_id` -- which Sense run produced this row
- `sku`, `node_id` (null at cluster grain), `cluster_id`, `date` -- grain
- `p10`, `p50`, `p90` -- quantile forecast
- `model` -- `timesfm` or `arima_xreg`
- `method` -- concrete rule used (e.g. `ai_forecast_timesfm`, `arima_plus_xreg`, `seasonal_naive_xreg` for the local mirror)
- `includes_plays` -- whether this run's `future_regressors` carried an approved play
- `as_of` -- the forecast's origin date

### `gaps` (14)
- `tenant_id`, `gap_id`, `run_id`
- `type` -- one of the five gap types, see below
- `sku`, `node_id`, `batch_id` (null for stockout_risk)
- `units_at_risk` -- units driving the rupee figure
- `deadline_date`, `deadline_type` (`online_sellby` / `expiry` / `lead_time`)
- `rupees_at_stake` -- see the recomputation rule below
- `evidence` -- fixed STRUCT: `on_hand`, `projected_sellthrough`, `forecast_run_id`,
  `sellby_rule` (the version string), `inbound`, `unit_cost`, `margin_per_unit`,
  `counterpart_node_id`, `counterpart_units` (rebalance only)
- `created_at`

### `plays` (15)
- `tenant_id`, `play_id`, `gap_id`, `status`, `objective`, `mechanic`, `channel`, `sku`
- `target_node_ids`, `target_batch_ids` -- denormalised from `play_json.target` for pruning
- `window_start`, `window_end` -- Measure's join window
- `policy_version`, `created_at`, `approved_at`
- `play_json` -- the full Play object (`docs/schemas/play.schema.json`); the scalar columns above
  are denormalised copies of parts of it, kept in sync by the writer

### `play_assignments` (16)
- `tenant_id`, `play_id`, `customer_id`, `arm` (`treated`/`holdout`), `assigned_at`

### `conversations` (17) / `messages` (18)
- `conversations`: `tenant_id`, `session_id`, `customer_id`, `channel`, `play_id`, `started_at`
- `messages`: adds `message_id`, `role` (`user`/`agent`/`tool`), `text`, `tool_calls` (JSON),
  `citations` (JSON), `latency_ms`, `ts`

### `play_outcomes` (19)
- `tenant_id`, `play_id`, `arm`
- `customers`, `responders`, `units_target_lot`, `revenue`, `margin`, `discount_cost`, `waste_avoided`
- `lift`, `ci_low`, `ci_high` -- treated arm only, null unless `status = 'measured'`
- `status` (`measured`/`unmeasured`), `min_treated_n`
- `waste_kg_est`, `co2e_kg_est`, `emissions_factor_kgco2e_per_kg` -- see the emissions note below
- `net_margin_per_discount_inr` -- the CEO number, treated arm only
- `computed_at`

### `estimator_priors` (20)
- `tenant_id`, `mechanic`, `category`, `segment_id`, `alpha`, `beta` -- Beta prior parameters,
  `n_measured`, `updated_at`

### `execution_events` (21)
- `tenant_id`, `run_id`, `seq`, `ts`, `ts_offset_ms`, `agent`, `event_type`, `payload` (JSON) --
  one row per ADK event, replayable in order

### `eval_forecast` (22) / `eval_planner` (23) / `eval_copy` (24)
- `eval_forecast`: `tenant_id`, `run_id`, `origin_date`, `tier`, `model`, `mape`, `bias`,
  `n_series`, `computed_at` -- written by `data/bigquery/sense/backtest.sql`
- `eval_planner`: `tenant_id`, `run_id`, `gap_id`, `schema_valid`, `gate_pass`, `iterations`,
  `trajectory_match`, `mechanic`, `computed_at`
- `eval_copy`: `tenant_id`, `run_id`, `play_id`, `variant_idx`, `language`, `validator_pass`,
  `disclosure_included`, `regenerated`, `computed_at`

### `festival_calendar` (25)
- `tenant_id`, `name`, `date`, `window_days` (radius applied around `date`), `categories` --
  input to `future_regressors.is_festival`

### `forecast_explain` (26)
- `tenant_id`, `run_id`, `sku`, `cluster_id`, `date`, `time_series_type`, `trend`,
  `seasonal_period_yearly`, `seasonal_period_weekly`, `holiday_effect`, `xreg_on_promo`,
  `xreg_is_festival`, `residual` -- `ML.EXPLAIN_FORECAST` decomposition for the Play card's
  "why this forecast" drawer

### `substitutes` (27)
- `tenant_id`, `sku`, `candidates` (up to 5 same-category skus), `computed_at`

## The sell-by rule

FSSAI's advisory to e-commerce food business operators (December 2024) reads: delivered food
must have **"30 percent or 45 days before expiry at the time of delivery."** [measured: this is
the advisory's own wording, quoted verbatim] That wording is ambiguous about whether it means the
*later* or the *earlier* of the two cut-offs. Taal implements `sellby_rule` as a versioned policy
parameter (`config/tenant.demo.toml [sellby_rule]`, `agents/gate/sellby.py`) and defaults to the
**stricter reading**: `online_sellby_date = expiry_date - max(30% of shelf_life_days, 45 days)`.
The gap card shows the rule version on every online_sellby_breach gap; the README and deck state
plainly that a retailer configures its own reading of the advisory, and that Taal does not claim
to interpret food-safety law -- it applies whichever rule the retailer sets.

## Daily sales generation rule

Quoted verbatim from `data/generator/generate.py`'s module docstring:

> Daily sales rule (stated so it can be checked): for each sku the weekly total at a typical node
> is velocity(category) x popularity(sku) x 7; it is spread to nodes by fixed node shares, to days
> by the day-of-week profile, lifted by festival windows and promo days, then multiplied by
> lognormal noise (sigma 0.25) and rounded to an integer.

This is **estimated/synthetic**, not measured retail behaviour; it exists to produce a plausible,
deterministic demo tenant, disclosed as such in the README and on the evaluation slide.

## Planted situations

Fixed ids, asserted by tests and used by the demo script (from `data/generator/generate.py` and
`jobs/sense/gaps.py`'s `PLANTED_IDS`):

| Situation | SKU | Node(s) | Gap type |
|---|---|---|---|
| Chips lot near online sell-by | `SKU-MASALA-CHIPS-200G` (batch `B-CHIPS-DS07-01`) | DS-07 | `online_sellby_breach` |
| Cola Zero stockout risk | `SKU-COLA-ZERO-500ML` | DS-07, DS-02 | `stockout_risk` |
| Kaju Katli festival stockout | `SKU-KAJU-KATLI-250G` | DS-01, DS-03 | `stockout_risk` |
| Quinoa slow mover | `SKU-QUINOA-500G` | OUT-02 | `slow_mover` |
| Darjeeling tea, policy beat | `SKU-DARJEELING-TEA-100G` | DS-04 | `online_sellby_breach` |

## Emissions factor note

`play_outcomes.emissions_factor_kgco2e_per_kg` is fixed at **2.5 kg CO2e per kg of food waste**
(`jobs/measure/run.py: EMISSIONS_FACTOR_KGCO2E_PER_KG`). This is an **estimate** used only to put
one impact line ("waste avoided" in CO2e terms) on the Outcomes screen and Looker Studio -- it is
not measured for this tenant, this region, or this product mix, and it is not used in any margin,
discount, or holdout calculation. Replace it with a tenant-specific factor (e.g. from a national
food-waste GHG inventory for the retailer's country) before quoting the CO2e line outside a demo
context; until then every surface that shows it must label it "estimate."
