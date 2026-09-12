-- Assertion: for plays with at least 200 assigned customers, the realised holdout share in
-- play_assignments is within 0.03 of the 0.10 default (DECISIONS §5.4, §17.3 "arm assignment
-- reproducible"). play_json's stored holdout fraction is not accessible portably (JSON access
-- differs between DuckDB and BigQuery), so this checks the actual assignment rows instead, using
-- only COUNT and CASE. Zero rows returned = pass.
SELECT
  tenant_id, play_id,
  COUNT(*) AS total_customers,
  SUM(CASE WHEN arm = 'holdout' THEN 1 ELSE 0 END) AS holdout_customers,
  SUM(CASE WHEN arm = 'holdout' THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS holdout_share
FROM play_assignments
GROUP BY tenant_id, play_id
HAVING COUNT(*) >= 200
  AND ABS(SUM(CASE WHEN arm = 'holdout' THEN 1 ELSE 0 END) * 1.0 / COUNT(*) - 0.10) > 0.03;
