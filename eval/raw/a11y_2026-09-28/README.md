# Axe accessibility scan, 2026-09-28

One JSON file per route x viewport, from the real `web/tests/e2e/a11y.spec.ts` suite (axe-core via
`@axe-core/playwright`, tags `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`), against the mock-mode
local Next.js server (`NEXT_PUBLIC_TAAL_MOCK=1`) -- no running API needed, every route gets real,
stable content. This is evidence the axe suite stayed green after the live-region and focus-order
changes in this branch (chat log `role="log"`, the approve result and re-plan result
`role="status"`, focus moved to the approve heading); it is not a new checklist item.

Produced with (the opt-in `TAAL_A11Y_REPORT_DIR` step added to `a11y.spec.ts` itself; unset, the
suite runs exactly as before and writes nothing):

```
cd web
TAAL_A11Y_REPORT_DIR=../eval/raw/a11y_2026-09-28 NEXT_PUBLIC_TAAL_MOCK=1 \
  npx playwright test tests/e2e/a11y.spec.ts --reporter=line
```

## Result

18 of 18 scans passed (9 routes x {desktop, phone}); 0 violations in every file.

| viewport | route | violations | passes | incomplete | inapplicable |
|---|---|---|---|---|---|
| desktop | / | 0 | 23 | 1 | 39 |
| desktop | /desk | 0 | 26 | 2 | 36 |
| desktop | /phone | 0 | 24 | 1 | 38 |
| desktop | /chat | 0 | 23 | 1 | 39 |
| desktop | /outcomes | 0 | 24 | 1 | 38 |
| desktop | /feedback | 0 | 24 | 1 | 38 |
| desktop | /feedback/results | 0 | 24 | 1 | 38 |
| phone (390x844) | / | 0 | 24 | 1 | 38 |
| phone (390x844) | /desk | 0 | 26 | 2 | 36 |
| phone (390x844) | /phone | 0 | 25 | 1 | 37 |
| phone (390x844) | /chat | 0 | 24 | 1 | 38 |
| phone (390x844) | /outcomes | 0 | 25 | 1 | 37 |
| phone (390x844) | /feedback | 0 | 25 | 1 | 37 |
| phone (390x844) | /feedback/results | 0 | 25 | 1 | 37 |

("incomplete" is axe's own count of checks it could not fully automate, e.g. ones needing a human
judgement call -- not a violation; every number above is measured, from the committed JSON files in
this directory, each carrying its own `axe_core_version` and `scanned_at` timestamp.)
