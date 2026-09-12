-- Assertion: gaps.rupees_at_stake, independently recomputed from gaps.units_at_risk and
-- products.unit_cost / list_price by gap type (write-off types: units_at_risk * unit_cost;
-- lost-margin types stockout_risk and unmet_demand: units_at_risk * (list_price - unit_cost)),
-- matches within 1 rupee. Zero rows returned = pass.
SELECT
  g.tenant_id, g.gap_id, g.type, g.rupees_at_stake,
  CASE WHEN g.type IN ('stockout_risk', 'unmet_demand')
       THEN g.units_at_risk * (p.list_price - p.unit_cost)
       ELSE g.units_at_risk * p.unit_cost
  END AS recomputed_rupees_at_stake
FROM gaps g
JOIN products p
  ON p.tenant_id = g.tenant_id AND p.sku = g.sku
WHERE ABS(
  g.rupees_at_stake -
  CASE WHEN g.type IN ('stockout_risk', 'unmet_demand')
       THEN g.units_at_risk * (p.list_price - p.unit_cost)
       ELSE g.units_at_risk * p.unit_cost
  END
) > 1;
