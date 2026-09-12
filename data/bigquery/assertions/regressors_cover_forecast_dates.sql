-- Assertion: every forecast (date, sku, cluster_id) has a future_regressors row.
-- Zero rows returned = pass.
SELECT DISTINCT f.tenant_id, f.date, f.sku, f.cluster_id
FROM forecasts f
LEFT JOIN future_regressors r
  ON r.tenant_id = f.tenant_id AND r.date = f.date AND r.sku = f.sku AND r.cluster_id = f.cluster_id
WHERE f.cluster_id IS NOT NULL
  AND r.date IS NULL;
