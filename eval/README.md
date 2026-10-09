# Evaluation outputs

Raw outputs live here so the numbers on the deck's slides and in the README are produced, not typed.

- `runs/` (gitignored): junit XML from `make status`, `adk eval` logs from `make eval`, Playwright reports.
- Committed at freeze (2 Oct): the filled evaluation table (`evaluation.md`), the planner evalset
  results, the Agent Simulation guardrail pass rate, the vision accuracy table on the 30 staged
  photos, latency logs and the billing export summary (DECISIONS §12).

- `raw/feedback_summary_<date>/summary.{json,md}`: practitioner feedback, written only by
  `make feedback-summary` from real responses (`source: "real"`; test rows are counted as excluded,
  never aggregated). Every figure is split by `mode` (self-filled vs filled in by the team during an
  interview); below 8 answers a cell is a count, not a percentage. These two files are the only
  source for any feedback number in the deck. The current one is `raw/feedback_summary_2026-10-09/`
  (7 usable responses; 3 excluded via `config/feedback_exclusions.json`).

Nothing in this folder is a pilot result until `docs/pilot.md` says so.
