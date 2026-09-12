-- Assertion: for every food inventory_batches row, online_sellby_date <= expiry_date.
-- Zero rows returned = pass.
SELECT b.tenant_id, b.batch_id, b.sku, b.node_id, b.online_sellby_date, b.expiry_date
FROM inventory_batches b
JOIN products p
  ON p.tenant_id = b.tenant_id AND p.sku = b.sku
WHERE p.is_food = TRUE
  AND b.online_sellby_date IS NOT NULL
  AND b.expiry_date IS NOT NULL
  AND b.online_sellby_date > b.expiry_date;
