-- Assertion: every customer has at least one consent row. Zero rows returned = pass.
SELECT c.tenant_id, c.customer_id
FROM customers c
LEFT JOIN consent co
  ON co.tenant_id = c.tenant_id AND co.customer_id = c.customer_id
WHERE co.customer_id IS NULL;
