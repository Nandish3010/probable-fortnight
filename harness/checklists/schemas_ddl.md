---
component: schemas_ddl
title: Schemas and DDL
owner: D
spec_sections: ["2.4", "3.3", "17.1"]
tests: ["tests/contract", "tests/sql/test_ddl.py"]
---
# Schemas and DDL

Source of truth: `docs/schemas/play.schema.json` drives BigQuery DDL, Pydantic models and TS types.

## Deterministic (CI gate)
- [x] JSON Schema validates 20 golden plays under `fixtures/plays/valid/`
- [x] JSON Schema rejects 20 mutated plays under `fixtures/plays/invalid/` (missing citation, holdout < 0.05, negative units)
- [x] DDL in `data/bigquery/ddl/` applies on a fresh DuckDB/BigQuery dataset
- [x] Every large table has a partition and cluster spec (`sales_daily`, `orders`, `order_lines`, `forecasts`, `messages`)
- [x] Pydantic models regenerate from the schema with no diff (`tests/contract`)
- [x] TypeScript types regenerate from the schema with no diff

## Reviewer-verified
- [x] Schema matches §2.4 field-for-field (names, enums, required, nesting) — audited `docs/schemas/play.schema.json` against the §2.4 sketch line by line: every field, nesting and enum in the prose is present with matching values (`objective`'s 5 values, `mechanic`'s 8, `target.deadline_type`'s 3, `copy.copy_status`'s 4, `status`'s 7, `holdout.fraction >= 0.05`). Six real, code-justified fields exist beyond the prose sketch (which predates the Cost Governor and some later decisions) and are not drift: top-level `tenant_id`; `mechanic_params.transfer_units` (used by the `transfer_plus_nudge` formula in `agents/gate/estimator.py`); a 6th `citations[].type` value `"stock"` (written by `agents/planner/drafting.py:145`); `alternatives[]` carrying flattened `expected_units`/`expected_margin_inr`/`rejected_because` instead of a nested `expected_outcome` (matches how `web/app/desk/page.tsx` actually renders "Why this play?"); and the top-level `cost` object (§18, added after §2.4 was written)
- [x] Tool schemas under `docs/schemas/tools/` match the §5.3 and §5.5 tool contracts
