-- 07_substitutes.sql
-- Substitute candidates: embed product name+category, VECTOR_SEARCH top-5 same-category
-- candidates per SKU into `taal.substitutes` (DECISIONS §5.2 step 6). Stock filtering happens at
-- chat time against Firestore (find_substitutes tool), not here.
--
-- Two equivalent embedding paths exist depending on which is enabled for the project:
--   (a) AI.GENERATE_EMBEDDING -- the newer unified generative-AI SQL surface.
--   (b) ML.GENERATE_EMBEDDING over a remote model pointed at a Vertex text embedding endpoint
--       (CREATE OR REPLACE MODEL ... REMOTE WITH CONNECTION ... OPTIONS(endpoint='...')).
-- This script uses (a); switch to (b) unchanged in shape if AI.GENERATE_EMBEDDING is
-- unavailable in the deployment region. VERIFY: exact function name/args for the BigQuery
-- release used at deploy time -- both spellings have existed across preview stages.
--
-- Params: @tenant_id STRING, @as_of DATE, @run_id STRING.

CREATE TEMP TABLE product_text AS
SELECT
  tenant_id, sku, category,
  CONCAT(name, ' -- ', category) AS text_input
FROM `taal.products`
WHERE tenant_id = @tenant_id;

CREATE TEMP TABLE embedded AS
SELECT
  sku, category, ml_generate_embedding_result AS embedding
FROM AI.GENERATE_EMBEDDING(
  MODEL `taal.text_embedding_model`,  -- remote model over a Vertex text-embedding endpoint; created once in infra/deploy.sh
  TABLE product_text,
  STRUCT('text_input' AS content_column)
);

CREATE TEMP TABLE ranked AS
SELECT
  base.query.sku AS sku,
  base.query.category AS category,
  base.query.sku != base.base.sku AS is_other_sku,
  base.base.sku AS candidate_sku,
  base.distance
FROM VECTOR_SEARCH(
  TABLE embedded, 'embedding',
  TABLE embedded, 'embedding',
  top_k => 6   -- 5 candidates + itself, filtered below
) AS base
WHERE base.query.category = base.base.category
QUALIFY ROW_NUMBER() OVER (PARTITION BY base.query.sku ORDER BY base.distance) <= 6;

DELETE FROM `taal.substitutes` WHERE tenant_id = @tenant_id;

INSERT INTO `taal.substitutes` (tenant_id, sku, candidates, computed_at)
SELECT
  @tenant_id,
  sku,
  ARRAY_AGG(candidate_sku ORDER BY distance LIMIT 5) AS candidates,
  CURRENT_TIMESTAMP() AS computed_at
FROM ranked
WHERE is_other_sku
GROUP BY sku;
