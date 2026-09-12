-- Assertion: p10 <= p50 <= p90 for every forecast row. Zero rows returned = pass.
SELECT tenant_id, run_id, sku, node_id, date, p10, p50, p90
FROM forecasts
WHERE NOT (p10 <= p50 AND p50 <= p90);
