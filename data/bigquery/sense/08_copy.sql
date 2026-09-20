-- 08_copy.sql
-- The "fuller" copy-generation path from DECISIONS §5.2 step 7 (read approved plays and
-- products back out of BigQuery). NOT YET WIRED UP: nothing in this codebase writes rows to
-- `taal.plays` or `taal.products` -- LocalStore is the system of record -- so the two SELECTs
-- below currently return nothing against a real dataset. The path that actually runs today is
-- the minimal one in jobs/sense/copy.py::generate_copy_bigquery, called from
-- services/api/approve.py at approve time: it builds variant_requests in Python from the play
-- already in memory instead of reading it back from BigQuery, and skips straight to the
-- AI.GENERATE_TABLE call below. This file is kept as the intended fuller version for whoever
-- wires up the BigQuery/Firestore sync (see infra/README.md); do not treat it as executed.
--
-- AI.GENERATE_TABLE over a Vertex-connected remote model, output schema copy_text STRING,
-- disclosure_included BOOL, reason STRING. One variant per segment x language. Discount numbers
-- and the best-before date are passed as constants in the prompt with an explicit "copy exactly"
-- instruction so the model cannot invent a different number; the validator query below
-- re-checks that anyway, and the Python validator (jobs/sense/copy.py::validate_copy) is the
-- actual gate regardless of which path produced the text.
--
-- The model id is never written here: {{COPY_MODEL}} is a template placeholder resolved from
-- config/models.toml (agents.gate.config.load_models()["ids"]["flash"] -- not flash_lite, which
-- 404s in asia-south1; see the comment in models.toml) before this script is submitted to
-- BigQuery, and the remote model itself is created once in infra/deploy.sh pointing at that same
-- id via a Vertex AI connection -- never a literal model string inside this file. The model id
-- contains dots (gemini-2.5-flash), which BigQuery would otherwise mis-parse as extra path
-- segments in a single backtick-quoted identifier (confirmed by actually hitting that error
-- while wiring up the minimal path) -- {{COPY_MODEL}} here is already the dot-free resource name
-- (id.replace(".", "_") + "_remote"), matching what infra/deploy.sh creates.
--
-- Params: @tenant_id STRING, @as_of DATE, @run_id STRING.

CREATE TEMP TABLE approved_plays AS
SELECT
  pl.play_id, pl.sku, pl.mechanic, pl.policy_version, p.name AS sku_name,
  JSON_VALUE(pl.play_json, '$.mechanic_params.discount_pct') AS discount_pct,
  JSON_VALUE(pl.play_json, '$.mechanic_params.bundle_price') AS bundle_price,
  JSON_VALUE(pl.play_json, '$.target.deadline_type') AS deadline_type,
  JSON_VALUE(pl.play_json, '$.target.deadline_date') AS deadline_date,
  JSON_EXTRACT_ARRAY(pl.play_json, '$.audience.segment_ids') AS segment_ids
FROM `taal.plays` pl
JOIN `taal.products` p ON p.tenant_id = pl.tenant_id AND p.sku = pl.sku
WHERE pl.tenant_id = @tenant_id AND pl.status = 'approved';

CREATE TEMP TABLE variant_requests AS
SELECT
  ap.play_id, ap.sku, ap.mechanic, ap.sku_name, ap.discount_pct, ap.bundle_price,
  ap.deadline_type, ap.deadline_date,
  seg.segment_id,
  lang AS language,
  CONCAT(
    'Write one short, plain, non-pushy message in ', lang, ' for a grocery customer. ',
    'Product: ', ap.sku_name, '. Mechanic: ', ap.mechanic, '. ',
    IF(ap.discount_pct IS NOT NULL, CONCAT('Discount: ', ap.discount_pct, '% -- copy this number exactly, do not change it. '), ''),
    IF(ap.bundle_price IS NOT NULL, CONCAT('Bundle price: Rs ', ap.bundle_price, ' -- copy this number exactly. '), ''),
    IF(ap.deadline_type = 'online_sellby', CONCAT('State the best-before date ', ap.deadline_date, ' plainly. '), ''),
    'Do not invent any other number or date. Keep it under 40 words. ',
    'Output disclosure_included = true only if the best-before date appears verbatim in copy_text.'
  ) AS prompt_text
FROM approved_plays ap
CROSS JOIN UNNEST(ap.segment_ids) AS segment_id_json
CROSS JOIN UNNEST(['en', 'kn']) AS lang
LEFT JOIN (SELECT segment_id_json AS raw, TRIM(segment_id_json, '"') AS segment_id) seg
  ON TRUE;

-- AI.GENERATE_TABLE over the remote model (see comment above on the placeholder).
CREATE TEMP TABLE generated AS
SELECT
  vr.play_id, vr.segment_id, vr.language, vr.deadline_type, vr.deadline_date,
  vr.discount_pct, vr.bundle_price,
  g.copy_text, g.disclosure_included, g.reason
FROM AI.GENERATE_TABLE(
  MODEL `taal`.`{{COPY_MODEL}}`,  -- resolved by the Sense job; see header comment
  TABLE variant_requests,
  STRUCT('prompt_text' AS prompt_column),
  output_schema => 'copy_text STRING, disclosure_included BOOL, reason STRING'
) g
JOIN variant_requests vr USING (play_id, segment_id, language);

-- Validator: reject a variant whose copy_text does not contain the exact discount/price number,
-- or that lacks the best-before date on a near-deadline mechanic. Rejected rows are flagged for
-- one automatic regeneration by the Sense job (not expressed in SQL); a rejection that survives
-- regeneration falls back to the templated copy in agents/gate (never a blank offer).
CREATE TEMP TABLE validated AS
SELECT
  play_id, segment_id, language, copy_text, disclosure_included, reason,
  (deadline_type != 'online_sellby' OR STRPOS(copy_text, deadline_date) > 0) AS has_required_disclosure,
  (discount_pct IS NULL OR STRPOS(copy_text, CAST(discount_pct AS STRING)) > 0) AS discount_matches,
  (bundle_price IS NULL OR STRPOS(copy_text, CAST(bundle_price AS STRING)) > 0) AS bundle_price_matches
FROM generated;

CREATE TEMP TABLE validated_pass AS
SELECT *,
  (has_required_disclosure AND discount_matches AND bundle_price_matches AND disclosure_included = has_required_disclosure) AS validator_pass
FROM validated;

DELETE FROM `taal.eval_copy` WHERE tenant_id = @tenant_id AND run_id = @run_id;

INSERT INTO `taal.eval_copy` (tenant_id, run_id, play_id, variant_idx, language, validator_pass, disclosure_included, regenerated, computed_at)
SELECT
  @tenant_id, @run_id, play_id,
  ROW_NUMBER() OVER (PARTITION BY play_id ORDER BY segment_id, language) AS variant_idx,
  language, validator_pass, disclosure_included, FALSE AS regenerated, CURRENT_TIMESTAMP()
FROM validated_pass;

-- Merge validated variants back onto the play (only the ones that passed; anything that failed
-- keeps copy_status = 'pending' at that segment x language and is left for the Sense job's
-- regeneration pass / templated fallback).
UPDATE `taal.plays` pl
SET play_json = JSON_SET(
  play_json,
  '$.copy.copy_status', 'validated'
)
WHERE pl.tenant_id = @tenant_id
  AND pl.status = 'approved'
  AND EXISTS (SELECT 1 FROM validated_pass v WHERE v.play_id = pl.play_id AND v.validator_pass);
