# "Prompt B" status: recorded Gemini (Vertex backend) planner trace for the Play Desk

## Conclusion

**No such PR or branch found.** [Certain]

"Prompt B" -- replacing the Play Desk's scripted/stub planner trace with a recorded Gemini
(Vertex backend) planner trace, wired into the image seed -- has not merged into `main`, is not
open as a pull request, and does not exist as an unmerged branch anywhere in this repository as
of this check (origin/main at `3e342e0`, 2026-09-27). `infra/Dockerfile.api` and
`harness/seed_plays.py` on `origin/main` still seed the Play Desk's demo plays with the
deterministic **stub** backend, by explicit design.

## Evidence

### 1. `origin/main` state and recent history

`git fetch origin` pulled one new merge onto `main` since the sweep's reference point (`ac82069`):

```
3e342e0 Merge pull request #42 from Nandish3010/bigquery-schema-migration-gaps-evidence
99b37a5 Migrate live taal.gaps schema; fix a BigQuery load bug; verify nightly path in staging
ac82069 Merge pull request #41 from Nandish3010/nightly-batch-in-bigquery-and-deck-fixes
```

`git log --oneline origin/main -15` (after the fetch) shows nothing else new; the two commits
after `ac82069` are BigQuery schema/load-bug work only -- neither touches the planner, the Play
Desk, `infra/Dockerfile.api`, or `harness/seed_plays.py`.

### 2. The image seed still uses the stub backend, on purpose

`infra/Dockerfile.api` (`origin/main`), the image that serves the Play Desk, seeds its demo
tenant like this:

```
# Seed the demo tenant into the image (mirrors `make generate`). ... Stub backend here on
# purpose -- the seeded plays are the golden fixtures; the vertex backend is a runtime setting.
RUN TAAL_MODEL_BACKEND=stub uv run python -m data.generator --out /app/.local/data --seed 20260912 \
 && TAAL_MODEL_BACKEND=stub uv run python -m jobs.sense \
 && TAAL_MODEL_BACKEND=stub uv run python -m harness.seed_plays
```

`harness/seed_plays.py`'s own docstring confirms the intent: it runs the Planner once per demo
gap "so the API, the web app and the tests find plays without a model call." `config/models.toml`
still defaults `backend = "stub"` project-wide ("stub" returns golden fixtures used in CI;
"vertex" calls Gemini through Vertex AI). None of this has changed on `main`.

Live/recorded **Vertex** planner traces do exist in the repo, e.g.
`eval/raw/rationale_judge_planner_runs_2026-09-21/` and
`eval/raw/planner_prompt_v6_2026-09-24/` -- but these are evaluation-run artifacts from live
Gemini calls made during prompt/schema-contract testing, not fixtures wired into
`fixtures/golden_runs/`, `web/mocks/`, or the `infra/Dockerfile.api` image-seed path that actually
supplies the Play Desk's default (replay) trace. [Certain]

### 3. All 24 non-`main` remote branches checked; none do this

Every remote branch other than `main` was diffed against `origin/main` and separately searched for
any touch of `infra/Dockerfile.api`, `harness/seed_plays.py`, `fixtures/*`, or `web/mocks/*`. None
changes the seed backend or adds a recorded-trace fixture wired into the Play Desk:

| Branch | Status vs main | Relevant? |
|---|---|---|
| `add-impact-framing-and-citations` | open, unmerged | No -- README/Outcomes-page citation framing only |
| `add-practitioner-feedback-form` | fully merged (PR #40) | No -- feedback form |
| `bigquery-full-forecast-load` | open, unmerged | No -- BigQuery forecast load evidence |
| `bigquery-schema-migration-gaps-evidence` | fully merged (PR #42) | No -- schema migration |
| `bigquery-store-system-of-record` | open, unmerged (PR #34) | No -- BigQuery system-of-record + Vertex AI **Sessions** (chat memory), not planner-trace recording |
| `brave-fermi-gdchto` | open, unmerged | No -- apparel demand simulation |
| `correctness-defects` | open, unmerged | No -- guardrail/sandbox/measure fixes |
| `cost-measurement-modeled` | open, unmerged | No -- cost measurement |
| `deck-audit-close-gaps` | open, unmerged | No -- deck-audit doc/evidence round |
| `firestore-serving-cache` | fully merged (PR #36) | No -- Firestore serving cache for chat reads |
| `fix-customer-context-leak` | open, unmerged | No -- customer chat context fix |
| `fix-forecast-label-and-stale-docs` | fully merged (PR #38) | No -- stale-claims/naming-regression fixes; only touches `fixtures/golden_runs/approve_chips.json` and `web/mocks/approve.json` (2-line unrelated tweak) |
| `gallant-knuth-u37sth` | fully merged (PR #30) | No -- demo UX/a11y/trace-panel **display** fixes, not trace sourcing; only touches `web/mocks/health.json` |
| `nightly-batch-in-bigquery-and-deck-fixes` | fully merged (PR #41) | No -- nightly BigQuery batch path |
| `planner-schema-contract-fix` | fully merged (PR #32) | Closest, but **no** -- fixes real planner prompt/schema-contract bugs and surfaces `planner_source` in `web/app/desk/page.tsx`; adds live-Vertex evaluation traces under `eval/raw/`, but does not touch `infra/Dockerfile.api`, `harness/seed_plays.py`, or `fixtures/golden_runs/` |
| `reframe-innovation-domain-agnostic-play` | open, unmerged | No -- README/DECISIONS framing |
| `remove-stylist-from-pitch` | fully merged (PR #39) | No -- removes stylist from pitch |
| `split-decisions-doc` | open, unmerged | No -- doc restructuring only |
| `stylist-garment-icons` | open, unmerged | No -- stylist garment icons; only touches `web/mocks/stylist_chat.json` |
| `vertex-ai-sessions` | fully merged (PR #35) | Closest-sounding name, but **no** -- adds a real Vertex AI **Sessions** backend for chat/conversation memory, decoupled from the model backend; unrelated to the Planner's trace |
| 4 further branches with a vendor-prefixed naming scheme | 2 already fully merged into main (empty diff); the other 2 touch only session-simulation test files and a batch of unrelated image files | No -- names omitted per this job's rule against writing AI-assistant names into files; none touch the paths in question either way |

("fully merged" = confirmed both by a `Merge pull request #N` commit in `origin/main`'s history
*and* an empty `git diff origin/main...origin/<branch>`; "open, unmerged" = non-empty diff and no
corresponding merge commit on `main`.)

### 4. GitHub pull requests (read-only; nothing commented, reviewed, merged or created)

**Open PRs on `Nandish3010/probable-fortnight`: none.** `list_pull_requests` with `state: open`
returned an empty list.

**15 most recently updated closed PRs:**

| # | Title | Merged | Merged at (UTC) | Touches Dockerfile.api/seed_plays.py/recorded trace? |
|---|---|---|---|---|
| 42 | Migrate live taal.gaps schema, fix a BigQuery load bug, verify nightly path in staging | Yes | 2026-09-27T18:54:45Z | No |
| 41 | Nightly BigQuery batch path: fix data-loss bug, correct billing record, deck-fix UI polish | Yes | 2026-09-27T18:09:39Z | No |
| 40 | Add an in-app practitioner feedback form | Yes | 2026-09-26T14:24:01Z | No |
| 39 | Take the stylist out of the pitch; keep its code | Yes | 2026-09-26T09:15:06Z | No |
| 38 | Fix three stale claims and a naming regression sweep | Yes | 2026-09-24T17:41:41Z | No |
| 37 | Make Outcomes carry the impact story: portfolio, honest counterfactual axis, expected-vs-measured | Yes | 2026-09-24T15:14:41Z | No |
| 36 | Add Firestore serving cache for chat-time reads, decoupled from other backends | Yes | 2026-09-24T04:23:03Z | No |
| 35 | Add real Vertex AI Sessions backend, decoupled from model backend | Yes | 2026-09-24T03:58:20Z | No (session/memory backend, not planner trace) |
| 34 | Add BigQueryStore: real system of record for 5 tables, verified, not yet wired live | Yes | 2026-09-24T03:27:52Z | No |
| 33 | Load full sales_daily/future_regressors into BigQuery, verify ARIMA_PLUS_XREG at 20-series scale | Yes | 2026-09-24T03:24:40Z | No |
| 32 | Fix real planner prompt/schema contract mismatches, surface planner_source | Yes | 2026-09-24T03:05:27Z | No (schema fixes + UI label, not the seed) |
| 30 | Fix demo UX defects: gap-card clock, dead links, live tests, trace panel, layout, a11y, mobile | Yes | 2026-09-24T02:25:58Z | No |
| 27 | Simulate real apparel demand for the stylist's style_requests | Yes | (2026-09-24, ~02:19Z window) | No |
| 28 | Close six correctness defects (item 6): Wilson CI, real order lines, chat crash, sandbox auth hole, CORS, guardrail/citation fixes | Yes | (2026-09-24, ~02:19Z window) | No |
| 31 | Generate real post-approval order lines through the existing persona simulation | Yes | 2026-09-24T02:15:51Z | No |

(`merged` above was cross-checked directly for PR #42 via `pull_request_read` -- `merged: true` --
since the `list_pull_requests` tool's own `merged` field reads `false` for every closed PR
regardless of actual status, a known quirk of that endpoint's list view; `merged` status for the
others is taken from `origin/main`'s own `Merge pull request #N` commits, which is authoritative.)

A `search_pull_requests` query for `planner trace Gemini recorded Play Desk scripted` scoped to
this repo returned **0 results**. A repo-wide search (`git grep`, both the working tree and
`origin/main`) for "Prompt B" / "prompt_b" returned no hits anywhere in project files (only
unrelated matches inside third-party `.venv` package internals, e.g. a generic "Prompt blocked"
log string in an SDK dependency -- not this project's content).

## Bottom line

Nothing in this repository -- not `main`, not an open PR, not any of the 24 other remote
branches -- currently swaps the Play Desk's stub-seeded/scripted planner trace for a recorded
Gemini (Vertex backend) trace. The closest-related, already-merged work (PR #32, schema-contract
fixes + surfacing `planner_source`; PR #35, a Vertex AI Sessions backend for chat memory) does not
do this. [Certain]
