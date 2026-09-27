# Final grep (task item 10 / Task A) -- per-hit decisions

Command: `grep -rniE 'ML\.FORECAST|in production|legal|no tool|learns' README.md docs/ web/ agents/ --include='*.md' --include='*.py' --include='*.ts' --include='*.tsx' --include='*.json' --exclude-dir=node_modules --exclude-dir=.next --exclude-dir=playwright-report --exclude-dir=test-results`

Full command output (pre-fix and post-fix) is in `final_grep.txt`. This file gives the
fix-or-leave decision and reasoning for every one of the 31 pre-fix hits. Line numbers below are
the **pre-fix** numbers (matching `final_grep.txt`'s first block); two `docs/privacy.md` rows
shifted by +2 after the fix (noted below) since an earlier fix inserted two lines above them.

| File:line | Matched text (short) | Decision | Reason |
|---|---|---|---|
| `README.md:52` | "never a hard-coded legal requirement" | **Fixed** | Reworded to "a tenant parameter, not hard-coded" (task known-leftover item e; the FSSAI rule is an advisory, not a hard-coded legal mandate). |
| `docs/privacy.md:89` (now :91) | "not a legal opinion" | Left | Refers to a real law (DPDP Act / India's DPDP Rules 2025) in the privacy threat-model framing -- the task's own example leave-reason ("'legal' referring to a real law, such as the DPDP Act in docs/privacy.md"). |
| `docs/privacy.md:115` (now :117) | "In production, Firestore..." | Left | Accurate: `infra/deploy.sh:199` sets `TAAL_FEEDBACK_STORE=firestore` on `taal-agents`, so Firestore genuinely does store practitioner feedback in the deployed service. Confirmed by reading `infra/deploy.sh`. |
| `docs/architecture.md:89` | "BigQuery `ML.FORECAST`... verified separately" | Left | Accurate, this sweep's own item-1 fix: cites `eval/raw/bigquery_arima_xreg_forecast_2026-09-23.json` and correctly states it is not on the approve path. |
| `docs/architecture.md:111` (now :114) | same, in the latency table | Left | Same as above; item-1 fix, accurate and cited. |
| `docs/DECISIONS.md:3` | "sells it first: legally" | Left | Positioning-line tagline, historical design record; covered by the as-built note's bullet 1 (lines 8-11), which explicitly says to read "legally" below as the regulator's advisory. |
| `docs/DECISIONS.md:10-11` | "legal deadline\", \"legally\"..." | Left | This *is* the as-built correction note itself, not a problem -- it defines how to read "legal"/"legally" elsewhere in the document. |
| `docs/DECISIONS.md:15` | "BigQuery `ML.FORECAST`... verified separately" | Left | Part of the as-built note; accurate and matches item 1's architecture.md wording. |
| `docs/DECISIONS.md:49` | "run in production, scalability" | Left | Generic hackathon-submission requirement text (what the documentation PDF must cover), not a claim about this repo's current deployed state. |
| `docs/DECISIONS.md:76` | "### 2.3 Gap types and the legal deadline" | Left | Section heading, original design-record text (rule 3c: "DECISIONS history not rewritten"); covered by the as-built note's bullet 1 and by the dated "Superseded" note immediately inside that same subsection (added by an earlier agent, a few lines below the heading). |
| `docs/DECISIONS.md:191` | data-flow line ("`ML.FORECAST`... Looker Studio") | Left | §4.2 Data flow, historical design record. Not adjacent to its own "Superseded" pointer, but covered by the as-built note's blanket statement at the top of the file ("where it differs from what the deployed code does, this note wins") plus its bullets 2 and 4 (approve re-forecast backend; Firestore/serving-cache status), which directly address this line's claims. |
| `docs/DECISIONS.md:194` | latency-budget line ("single-series `ML.FORECAST`...") | Left | §4.3 Latency budget -- has its own adjacent "**Superseded 27 Sep 2026:** see the as-built note at the top." directly following this paragraph. |
| `docs/DECISIONS.md:254` | "ML.FORECAST · live · 11.3 s" (judge-mode landing copy) | Left | Has its own adjacent Superseded note directly below this bullet. |
| `docs/DECISIONS.md:455` | "Legal online sell-by is invisible to" (slide-2 mockup) | Left | Inside "## 11. Deck", covered by the "**Superseded 27 Sep 2026**" note at the end of that section (line 486-487). |
| `docs/DECISIONS.md:471` | "The estimator learns: every Measure run" | Left | Same section-11 coverage as above; also independently a legitimate "learns" usage -- describes `update_prior()`, which the code does (`agents/gate/estimator.py`, `jobs/measure/run.py`), matching the task's own example leave-reason for "learns". |
| `docs/DECISIONS.md:484` | "The legal deadline" (deck full order) | Left | Same section-11 coverage (Superseded note at line 486-487). |
| `docs/DECISIONS.md:508` | "opens on the legal-deadline hook" (submission checklist) | Left | §13 checklist item (a to-do, not a claim about current state); "legal-deadline hook" is the same phrase the as-built note's bullet 1 explicitly redefines ("legal deadline" is one of the four quoted terms). |
| `docs/DECISIONS.md:521` | "`ARIMA_PLUS_XREG`... for `ML.FORECAST`" (pre-build checklist) | Left | §14 "Verify before building" -- a day-1-3 research to-do, not a claim about what the deployed code does today. |
| `docs/DECISIONS.md:611` | "min-instances=0 in production" | Left | Accurate and unrelated to the FSSAI/backend overclaims this sweep targets: independently verified as the actual deployed Cloud Run scaling decision (cites `eval/evaluation.md`'s measured cold-start numbers). |
| `docs/scale.md:87` | "BigQuery `ML.FORECAST`... verified separately" | Left | Accurate, item-1-consistent fix already in place; cites the same evidence file. |
| `docs/deck_audit.md:28` | "the legal deadline as a forecast covariate" | Left | Dated, point-in-time audit record (opens "Repo at commit `de1fe38` when this audit started"), not one of the task's named files and not touched by any prior agent in this sweep. The underlying code claim it stands for (Taal's code does see/act on the online sell-by cut-off) remains true; "legal" here is the audit's own shorthand, not a fresh claim. |
| `docs/deck_audit.md:29` | "estimator that learns from measurement" | Left | Same dated audit; legitimate "learns" usage per the task's own example (Measure's `update_prior()`). |
| `docs/deck_audit.md:53` | "isn't in production yet" | Left | Accurate: correctly describes the local-model-vs-BigQuery distinction this sweep independently confirmed (BigQuery `ARIMA_PLUS_XREG`/`AI.FORECAST` verified but not wired into the approve path or any job). |
| `docs/deck_audit.md:151` | "Sees the legal sell-by deadline?" | Left | This is the audit's "Claim as written" column -- a verbatim quote of the deck's own on-screen slide text. Rewording it here would misrepresent what the (unedited, binary) `docs/deck.pdf` actually says, i.e. fabricate a quote (rule 7). The verdict itself (TRUE: the code does see the online sell-by cut-off) is accurate regardless of the word choice. |
| `docs/deck_audit.md:210` | "`ML.FORECAST (local_seasonal_xreg)`" audit row | Left | Accurate historical record of a real, already-applied fix; matches current `services/api/approve.py` behavior exactly. |
| `web/mocks/health.json:13` | "Firestore is provisioned in production but this process never queries it" | Left | Generated mock fixture -- rule 3 explicitly forbids editing `web/mocks/*.json`. Confirmed never rendered: the only consumer, `web/components/HealthStrip.tsx`, reads `name`/`checked_at`/`ok` per check and never reads `.detail`. |
| `agents/gate/sellby.py:15` | "not a fixed legal interpretation" | Left | Pre-existing text, not touched by this sweep's diff, and already correctly hedged (explicitly says the rule is *not* a fixed legal interpretation). |
| `agents/planner/prompts/CHANGELOG.md:57` | "guardrail-legal" | Left | Prompt-iteration changelog jargon meaning "passes the deterministic guardrails" -- unrelated to FSSAI or any real-law claim. |
| `agents/README.md:6` | "Gemini via Vertex in production" | Left | Accurate: `infra/deploy.sh:199` sets `TAAL_MODEL_BACKEND=vertex` on the deployed `taal-agents` service (stub is only for CI). Confirmed by reading `infra/deploy.sh`. |
| `agents/stylist/prompts/stylist.md:37` | "no tool call" | Left | Incidental regex match ("no tool call" contains the substring "no tool") -- about the stylist agent's STOP handling (it never markets, so nothing to withdraw), unrelated to any "no forecasting tool sees X" claim. |

**Summary:** 31 hits, 1 fixed (`README.md:52`), 30 left in place with a documented reason. Two
`docs/privacy.md` line numbers shift to 91/117 in the post-fix run only because of an unrelated
earlier fix (task known-leftover item b) inserting two lines above them, not because those hits
themselves changed.
