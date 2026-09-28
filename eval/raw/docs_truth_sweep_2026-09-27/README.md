# Docs truth sweep (2026-09-27) -- evidence index

One line per file in this directory: what it holds, and the command or script that produced it.
`__pycache__/` is not listed -- it is gitignored (`git check-ignore` confirms both `.pyc` files
under it are matched by the repo's top-level `__pycache__/` rule).

- `commands.txt` -- every shell command actually run for this sweep, in order (Read/Grep tool
  calls are a separate mechanism and are not shell commands, so they are cited directly in the
  `source` fields of the JSON files below instead).
- `impact_numbers.py` -- script that reproduces the README "Impact in numbers" table from
  committed repo files only (no network, no scratch tenant). Run: `python3
  eval/raw/docs_truth_sweep_2026-09-27/impact_numbers.py` from the repo root.
- `impact_numbers.json` -- stdout/output of `impact_numbers.py`.
- `hook_numbers.py` -- script that reproduces the README "hook" numbers (`gap_chips_ds07` /
  `play_chips_ds07_v1`) by calling `services.api.approve.approve(...)` for real, the way
  `services/api/main.py`'s `POST /approve` route does, against a scratch tenant seeded by
  `data.generator`, `jobs.sense` and `harness.seed_plays` (exact commands and env vars in
  `commands.txt`). Run: `uv run python eval/raw/docs_truth_sweep_2026-09-27/hook_numbers.py`.
- `hook_numbers.json` -- stdout/output of `hook_numbers.py`.
- `tenant_counts.json` -- grocery/apparel SKU, node, customer and sales-history-day counts
  recounted directly from the scratch tenant's raw JSONL tables and cross-checked against its
  `manifest.json`; produced by the inline Python block in section 10 of `commands.txt`.
- `fetch_log.txt` -- timestamped log of every outbound network fetch attempted in this sweep
  (`curl` and the WebFetch/WebSearch tools) and its result.
- `fssai_citation.json` -- the search for a primary source for the FSSAI online-sell-by rule: one
  candidate PDF URL found on `fssai.gov.in` via WebSearch, never fetched (blocked), plus every
  secondary source tried and blocked.
- `winkelmann_abstract.json` -- attempt to check the README's paraphrase of the Winkelmann et al.
  arXiv paper against its actual abstract; the page was unreachable, so every claim is marked
  unverifiable rather than guessed.
- `otto_customer_story.json` -- sentence-by-sentence check of the README's OTTO/Google Cloud
  customer-story citation against the real page at `cloud.google.com/customers/otto`, fetched
  with `curl` through the session's proxy.
- `deployed_env_names.json` -- records that `TAAL_SESSION_BACKEND`/`TAAL_SERVING_CACHE` were not
  read from the live deployed service (no GCP credentials in this sandbox), with `infra/deploy.sh`
  read as the fallback evidence instead.
- `prompt_b_status.md` -- investigation of whether a "Prompt B" recorded-Gemini planner trace
  exists anywhere in this repo (`main`, all other remote branches, and GitHub PR history); finds
  no such trace and shows the evidence (git log/diff and the `github` MCP tools, read-only).
- `final_grep.txt` -- verbatim pre-fix and post-fix stdout of the sweep's closing grep for stale
  vendor/"legal"/"in production" wording: `grep -rniE 'ML\.FORECAST|in production|legal|no
  tool|learns' README.md docs/ web/ agents/ ...` (full command at the top of the file).
- `final_grep.md` -- the fix-or-leave decision and reasoning for each of the 31 hits in
  `final_grep.txt`.
- `web_checks.log` -- output of `npm run typecheck` and the mock-mode Playwright suite (`npm
  test`) run from `web/`.

Scratch-directory paths inside these files (`hook_numbers.py`, `hook_numbers.json`,
`tenant_counts.json`, `commands.txt`) were rewritten to `/tmp/sandbox-scratch/` -- a throwaway
tenant built fresh by `data.generator`/`jobs.sense`/`harness.seed_plays` for this sweep, never this
repo's own `.local/`. `fssai.gov.in` and `arxiv.org` (and its `export.arxiv.org` mirror) were
unreachable from the build sandbox: every attempt, by both `curl` and the WebFetch tool, was
rejected at the network egress proxy's CONNECT stage with HTTP 403 before reaching either site --
see `fetch_log.txt`, `fssai_citation.json` and `winkelmann_abstract.json` for the full detail.

**Added 2026-09-27, after rebasing this branch onto main at `98b3cb3`:** `deployed_env_names.json`
and `prompt_b_status.md` were produced against main at `52ffa0f`, before PR #48 (`98b3cb3`, "Scope
chat sessions and the Firestore serving cache to the visitor; keep both flags off") landed
`ENABLE_VERTEX_SESSIONS`/`ENABLE_SERVING_CACHE` in `infra/deploy.sh` and the
`agents/vertex_sessions.py`/`agents/gate/firestore_cache.py` visitor-isolation fixes. Both files
predate that merge and were not re-run against it; they are left as-is, point-in-time records.

- 28 Sep 2026, after rebasing onto main at 21b68d1: `make verify` green. The first `make live-test` run failed one test, `web/tests/live/judge.spec.ts:74` (health strip turns amber), with "route.fetch: Target page, context or browser has been closed"; main's own CI fails the same test the same way at 21b68d1, and this change touches no web test or health code. One re-run passed 15 of 15; that run is `live_test.log`.
