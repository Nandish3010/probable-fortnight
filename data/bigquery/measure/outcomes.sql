-- outcomes.sql
-- Mirrors jobs/measure/run.py exactly (DECISIONS §5.7): treated vs holdout per play, inside the
-- play window, into `taal.play_outcomes`.
--
-- responders   = customers in the arm with an order line carrying play_id, or the target sku at
--                a target node, inside [window.start, window.end]
-- lift         = treated response rate - holdout response rate
-- CI           = normal approximation, 95%: lift +/- 1.96 * sqrt(p_t(1-p_t)/n_t + p_h(1-p_h)/n_h)
-- status       = measured only if treated customers >= holdout.min_treated_n AND holdout
--                customers >= 1; otherwise unmeasured, and lift/ci_low/ci_high stay NULL
--                (DECISIONS §17.5: a lift without a holdout fails the job)
-- waste line   = units_target_lot x pack_weight_g / 1000 x EMISSIONS_FACTOR_KGCO2E_PER_KG (2.5,
--                an estimate -- see docs/DATA_MODEL.md)
-- CEO number   = net_margin_per_discount_inr = (treated margin - holdout margin scaled to
--                treated size) / treated discount cost
--
-- Params: @tenant_id STRING, @as_of DATE, @run_id STRING (min_treated_n is read per play from
-- `play_json` because it is set per play, not a single tenant constant, per the schema in
-- docs/schemas/play.schema.json `holdout.min_treated_n`).

DECLARE emissions_factor FLOAT64 DEFAULT 2.5;  -- kg CO2e per kg food waste; see docs/DATA_MODEL.md

CREATE TEMP TABLE eligible_plays AS
SELECT
  pl.play_id, pl.sku, pl.target_node_ids, pl.window_start, pl.window_end,
  CAST(JSON_VALUE(pl.play_json, '$.holdout.min_treated_n') AS INT64) AS min_treated_n,
  CAST(JSON_VALUE(pl.play_json, '$.target.units') AS INT64) AS units_at_risk,
  p.unit_cost, p.pack_weight_g
FROM `taal.plays` pl
JOIN `taal.products` p ON p.tenant_id = pl.tenant_id AND p.sku = pl.sku
WHERE pl.tenant_id = @tenant_id
  AND pl.status IN ('approved', 'running', 'measured', 'unmeasured');

CREATE TEMP TABLE arms AS
SELECT tenant_id, play_id, customer_id, arm
FROM `taal.play_assignments`
WHERE tenant_id = @tenant_id;

CREATE TEMP TABLE hits AS
-- an order line "hits" a play for a customer if it carries the play_id, or if it is the target
-- sku at a target node inside the window -- exactly jobs/measure/run.py's `hit` condition.
SELECT
  a.play_id, a.customer_id, a.arm,
  ol.qty, ol.price, IFNULL(ol.discount, 0.0) AS discount, ep.unit_cost
FROM arms a
JOIN eligible_plays ep ON ep.play_id = a.play_id
JOIN `taal.order_lines` ol
  ON ol.tenant_id = @tenant_id AND ol.customer_id = a.customer_id
  AND ol.ts BETWEEN ep.window_start AND ep.window_end
  AND (ol.play_id = a.play_id OR (ol.sku = ep.sku AND ol.node_id IN UNNEST(ep.target_node_ids)));

CREATE TEMP TABLE per_arm AS
SELECT
  ep.play_id, a.arm,
  COUNT(DISTINCT a.customer_id) AS customers,
  COUNT(DISTINCT h.customer_id) AS responders,
  IFNULL(SUM(h.qty), 0) AS units,
  IFNULL(SUM(h.qty * (h.price - h.discount)), 0.0) AS revenue,
  IFNULL(SUM(h.qty * (h.price - h.discount - h.unit_cost)), 0.0) AS margin,
  IFNULL(SUM(h.qty * h.discount), 0.0) AS discount_cost
FROM arms a
JOIN eligible_plays ep ON ep.play_id = a.play_id
LEFT JOIN hits h ON h.play_id = a.play_id AND h.customer_id = a.customer_id AND h.arm = a.arm
GROUP BY ep.play_id, a.arm;

CREATE TEMP TABLE wide AS
SELECT
  ep.play_id, ep.units_at_risk, ep.unit_cost, ep.pack_weight_g,
  t.customers AS n_t, IFNULL(t.responders, 0) AS r_t, IFNULL(t.units, 0) AS units_t,
  IFNULL(t.revenue, 0.0) AS revenue_t, IFNULL(t.margin, 0.0) AS margin_t, IFNULL(t.discount_cost, 0.0) AS discount_t,
  h.customers AS n_h, IFNULL(h.responders, 0) AS r_h, IFNULL(h.units, 0) AS units_h,
  IFNULL(h.revenue, 0.0) AS revenue_h, IFNULL(h.margin, 0.0) AS margin_h, IFNULL(h.discount_cost, 0.0) AS discount_h,
  ep.min_treated_n,
  (t.customers >= ep.min_treated_n AND IFNULL(h.customers, 0) >= 1) AS measurable
FROM eligible_plays ep
LEFT JOIN per_arm t ON t.play_id = ep.play_id AND t.arm = 'treated'
LEFT JOIN per_arm h ON h.play_id = ep.play_id AND h.arm = 'holdout';

CREATE TEMP TABLE rates AS
SELECT *,
  SAFE_DIVIDE(r_t, n_t) AS p_t,
  SAFE_DIVIDE(r_h, n_h) AS p_h
FROM wide;

CREATE TEMP TABLE with_lift AS
SELECT *,
  IF(measurable, p_t - p_h, NULL) AS lift,
  IF(measurable,
     (p_t - p_h) - 1.959964 * SQRT(SAFE_DIVIDE(p_t * (1 - p_t), n_t) + SAFE_DIVIDE(p_h * (1 - p_h), n_h)),
     NULL) AS ci_low,
  IF(measurable,
     (p_t - p_h) + 1.959964 * SQRT(SAFE_DIVIDE(p_t * (1 - p_t), n_t) + SAFE_DIVIDE(p_h * (1 - p_h), n_h)),
     NULL) AS ci_high
FROM rates;

DELETE FROM `taal.play_outcomes`
WHERE tenant_id = @tenant_id AND play_id IN (SELECT play_id FROM eligible_plays);

INSERT INTO `taal.play_outcomes`
  (tenant_id, play_id, arm, customers, responders, units_target_lot, revenue, margin, discount_cost,
   waste_avoided, lift, ci_low, ci_high, status, min_treated_n, waste_kg_est, co2e_kg_est,
   emissions_factor_kgco2e_per_kg, net_margin_per_discount_inr, computed_at)
SELECT
  @tenant_id, play_id, 'treated' AS arm, n_t, r_t, units_t, ROUND(revenue_t, 2), ROUND(margin_t, 2), ROUND(discount_t, 2),
  ROUND(LEAST(units_t, units_at_risk) * unit_cost, 2) AS waste_avoided,
  ROUND(lift, 6), ROUND(ci_low, 6), ROUND(ci_high, 6),
  IF(measurable, 'measured', 'unmeasured') AS status,
  min_treated_n,
  ROUND(LEAST(units_t, units_at_risk) * IFNULL(pack_weight_g, 0) / 1000.0, 3) AS waste_kg_est,
  ROUND(LEAST(units_t, units_at_risk) * IFNULL(pack_weight_g, 0) / 1000.0 * emissions_factor, 3) AS co2e_kg_est,
  emissions_factor,
  -- net_margin_per_discount_inr: only defined for treated, only when measurable and there was
  -- discount spend, mirroring jobs/measure/run.py's `ceo` value exactly.
  IF(measurable AND discount_t > 0,
     ROUND((margin_t - margin_h * SAFE_DIVIDE(n_t, n_h)) / discount_t, 4),
     NULL) AS net_margin_per_discount_inr,
  CURRENT_TIMESTAMP() AS computed_at
FROM with_lift

UNION ALL

SELECT
  @tenant_id, play_id, 'holdout' AS arm, n_h, r_h, units_h, ROUND(revenue_h, 2), ROUND(margin_h, 2), ROUND(discount_h, 2),
  ROUND(LEAST(units_h, units_at_risk) * unit_cost, 2) AS waste_avoided,
  CAST(NULL AS FLOAT64) AS lift, CAST(NULL AS FLOAT64) AS ci_low, CAST(NULL AS FLOAT64) AS ci_high,
  IF(measurable, 'measured', 'unmeasured') AS status,
  min_treated_n,
  ROUND(LEAST(units_h, units_at_risk) * IFNULL(pack_weight_g, 0) / 1000.0, 3) AS waste_kg_est,
  ROUND(LEAST(units_h, units_at_risk) * IFNULL(pack_weight_g, 0) / 1000.0 * emissions_factor, 3) AS co2e_kg_est,
  emissions_factor,
  CAST(NULL AS FLOAT64) AS net_margin_per_discount_inr,
  CURRENT_TIMESTAMP() AS computed_at
FROM with_lift;

-- push status back onto plays (treated arm's status governs the play's status), mirroring
-- run_measure()'s final step.
UPDATE `taal.plays` pl
SET
  status = po.status,
  play_json = JSON_SET(play_json, '$.status', po.status)
FROM (
  SELECT play_id, status FROM `taal.play_outcomes`
  WHERE tenant_id = @tenant_id AND arm = 'treated' AND play_id IN (SELECT play_id FROM eligible_plays)
) po
WHERE pl.tenant_id = @tenant_id AND pl.play_id = po.play_id;
