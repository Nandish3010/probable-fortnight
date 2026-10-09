Bulky traces live in the release asset `eval-raw-2026-09` (URL to be filled after release).

It holds 55 files, to be extracted at the repository root to restore them:

- `planner_traces_2026-09-28/gap_*.jsonl`: one recorded planner run per gap (50 files)
- `planner_real_traces_2026-09-28/run_0N/adk_events.jsonl`: raw agent event streams (5 files)

Everything else under `eval/raw/` is the summaries, scores and small result files that
`eval/evaluation.md` and the README cite. `python -m harness.build_fixtures --evalsets-from-traces
eval/raw/planner_traces_2026-09-28` needs the extracted traces.
