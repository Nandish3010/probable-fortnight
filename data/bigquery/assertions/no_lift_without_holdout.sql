-- Assertion (DECISIONS §17.5): any lift shown without a holdout fails. Violating rows are
-- play_outcomes rows with lift not null where no holdout row with customers >= 1 exists for
-- that play, or where status = 'unmeasured' but lift is not null. Zero rows returned = pass.
SELECT po.tenant_id, po.play_id, po.arm, po.lift, po.status
FROM play_outcomes po
LEFT JOIN play_outcomes h
  ON h.tenant_id = po.tenant_id AND h.play_id = po.play_id AND h.arm = 'holdout' AND h.customers >= 1
WHERE po.lift IS NOT NULL
  AND (h.play_id IS NULL OR po.status = 'unmeasured');
