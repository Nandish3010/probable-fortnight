# Tests

`make verify` runs them in this order and stops at the first red:

| Target | Directory | What |
|---|---|---|
| `schemas` | `tests/contract` | Play/Gap schema = Pydantic = TypeScript; 21 golden plays pass, 22 mutations fail; tool contracts validate live tool output; `docs/openapi.yaml` matches the app |
| `unit` | `tests/unit` | sell-by rule, estimator arithmetic and property tests, eight guardrails, hashed holdout within 1% on 10,000 ids, generator determinism and planted situations, measure maths |
| `sql` | `tests/sql` | DDL applies on DuckDB, partition/cluster present, eight assertion files return zero rows before and after approve + measure, gap rupees recomputed independently, re-forecast changes p50 only inside the play window |
| `agents` | `tests/agents` | planner on the planted gaps and the 50 largest gaps (validity, trajectory, <= 3 iterations, policy-change beat, Cost Governor), 20 scripted conversations, MCP round trip |
| `api-test` | `tests/api` | health, gaps, plays, idempotent approve with the chart moving, visitor isolation and scoped reset, chat SSE and JSON, rerun + events, capture/confirm/execution, outcomes never show a lift when unmeasured |
| `web-test` | `web/tests/e2e` | Playwright in mock mode: landing paints, 60-second beat, chat reply, phone golden path on mobile |
