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
- [ ] Schema matches §2.4 field-for-field (names, enums, required, nesting)
- [x] Tool schemas under `docs/schemas/tools/` match the §5.3 and §5.5 tool contracts
