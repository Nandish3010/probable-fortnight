-- priors_update.sql
-- Beta-Binomial prior update for measured plays: alpha += responders, beta += non-responders
-- (DECISIONS §3.4, §5.7). Run immediately after outcomes.sql in the same job so the "treated"
-- row it reads already reflects this run's measurement.
--
-- Params: @tenant_id STRING, @as_of DATE, @run_id STRING.

CREATE TEMP TABLE measured_treated AS
SELECT
  po.play_id, po.responders, po.customers,
  pl.mechanic, p.category
FROM `taal.play_outcomes` po
JOIN `taal.plays` pl ON pl.tenant_id = @tenant_id AND pl.play_id = po.play_id
JOIN `taal.products` p ON p.tenant_id = @tenant_id AND p.sku = pl.sku
WHERE po.tenant_id = @tenant_id
  AND po.arm = 'treated'
  AND po.status = 'measured'
  -- only plays freshly measured in this Measure run (join is by play_id; the calling job passes
  -- the same @run_id used by outcomes.sql's computed_at window if it needs to scope further)
  AND po.computed_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR);

-- segment_id is '*' here: the estimator's prior key is (mechanic, category, segment_id) but
-- Measure aggregates responders across the whole play, not per segment (jobs/measure/run.py
-- updates the prior with the play's total treated responders/non-responders under segment_id
-- = '*'); a future per-segment breakdown would need per-segment order_lines joins.
MERGE `taal.estimator_priors` p
USING (
  SELECT mechanic, category, '*' AS segment_id,
         SUM(responders) AS responders,
         SUM(customers - responders) AS non_responders,
         SUM(customers) AS n_measured
  FROM measured_treated
  GROUP BY mechanic, category
) m
ON p.tenant_id = @tenant_id AND p.mechanic = m.mechanic AND p.category = m.category AND p.segment_id = m.segment_id
WHEN MATCHED THEN
  UPDATE SET
    alpha = p.alpha + m.responders,
    beta = p.beta + m.non_responders,
    n_measured = p.n_measured + m.n_measured,
    updated_at = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN
  -- weak, disclosed prior for a (mechanic, category) pair never measured before (DECISIONS §3.4)
  INSERT (tenant_id, mechanic, category, segment_id, alpha, beta, n_measured, updated_at)
  VALUES (@tenant_id, m.mechanic, m.category, m.segment_id, 1.0 + m.responders, 19.0 + m.non_responders, m.n_measured, CURRENT_TIMESTAMP());
