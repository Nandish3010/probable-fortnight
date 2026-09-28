"""harness/record_flagship_traces.py: tool mechanics only, always with --allow-stub -- a real Vertex
recording needs live credentials this environment never has (see the module docstring). Reuses the
session-scoped demo tenant (tests/conftest.py::data_dir) as --base-data purely for speed: unlike a
real recording run, which builds its own tenant via data.generator + jobs.sense and deliberately
never runs harness.seed_plays, that shared fixture tenant already has every demo gap's play seeded.
That is harmless for what these tests check (the tool's own mechanics: independent per-run copies,
files written, a summary consistent with them, and the stub refusal) -- every run here still starts
from a fresh copy of that same --base-data root, and the assertions below confirm the shared root
itself is never touched by any of them."""
from __future__ import annotations

import json

from harness import record_flagship_traces as rpt

GAP_ID = "gap_tea_ds04"


def _base_play_count(data_dir, gap_id: str) -> int:
    rows = [json.loads(line) for line in (data_dir / "plays.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    return sum(1 for r in rows if r["gap_id"] == gap_id)


def test_refuses_stub_backend_without_allow_stub(tmp_path, monkeypatch):
    monkeypatch.setenv("TAAL_MODEL_BACKEND", "stub")
    out = tmp_path / "out"
    rc = rpt.main(["--gap", GAP_ID, "--runs", "1", "--out", str(out)])
    assert rc != 0
    assert not out.exists() or not any(out.iterdir()), "a refused run must not write anything to --out"


def test_allow_stub_runs_are_independent_and_summary_matches_the_files(tmp_path, data_dir, monkeypatch):
    monkeypatch.setenv("TAAL_MODEL_BACKEND", "stub")
    out = tmp_path / "out"
    before = _base_play_count(data_dir, GAP_ID)

    rc = rpt.main(["--gap", GAP_ID, "--runs", "2", "--out", str(out), "--allow-stub", "--base-data", str(data_dir)])
    assert rc == 0

    # the shared base tenant is never written to: each run only ever touches its own copy, so the
    # base's own play for this gap (from the fixture's own one-time seed_plays) is untouched --
    # still exactly the one row it started with, not duplicated or overwritten by either run.
    assert _base_play_count(data_dir, GAP_ID) == before

    assert (out / "flagship_gap.json").exists()
    gap_ctx = json.loads((out / "flagship_gap.json").read_text())
    assert gap_ctx["gap_id"] == GAP_ID and gap_ctx["gap"]["gap_id"] == GAP_ID
    assert isinstance(gap_ctx["candidate_audiences"], list)

    run_ids, results, plays = set(), {}, {}
    for i in (1, 2):
        run_dir = out / f"run_{i:02d}"
        for name in ("trace.jsonl", "adk_events.jsonl", "result.json", "play.json"):
            assert (run_dir / name).exists(), f"missing {name} for run {i}"
        result = json.loads((run_dir / "result.json").read_text())
        play = json.loads((run_dir / "play.json").read_text())
        results[i], plays[i] = result, play
        assert result["status"] == "proposed" and result["source"] == "scripted_stub"
        assert "error" not in result
        assert play["trace_ref"] == f"events/{result['run_id']}"
        run_ids.add(result["run_id"])

        trace_lines = [json.loads(line) for line in (run_dir / "trace.jsonl").read_text().splitlines() if line.strip()]
        assert trace_lines and trace_lines[-1]["kind"] == "run_summary"
        assert all(e["run_id"] == result["run_id"] for e in trace_lines), "this run's trace must not mix in another run's events"

        adk_lines = [json.loads(line) for line in (run_dir / "adk_events.jsonl").read_text().splitlines() if line.strip()]
        assert adk_lines, "the raw event_sink events must be captured too, not only the derived trace"

    assert len(run_ids) == 2, "each run must get its own run_id (a different salt per run)"
    # same gap/policy/mechanic on the same stub tenant copy -> the same play in substance; only the
    # run-specific fields (trace_ref, and the run_id it embeds) actually differ between the two.
    assert plays[1]["play_id"] == plays[2]["play_id"] and plays[1]["mechanic"] == plays[2]["mechanic"]
    assert plays[1]["trace_ref"] != plays[2]["trace_ref"]

    summary = json.loads((out / "summary.json").read_text())
    for key in ("recorded_at", "git_commit", "backend", "model", "prompt_version", "prompt_sha256", "thinking", "deadline_s", "taal_now", "gap_id", "runs", "aggregate"):
        assert key in summary, f"summary.json missing {key!r}"
    assert summary["gap_id"] == GAP_ID and summary["backend"] == "stub" and summary["model"] == "stub-planner"
    assert summary["prompt_version"].startswith("v") and len(summary["prompt_sha256"]) == 64
    assert summary["thinking"] == {"planner_route": "low", "planner_final": "medium", "customer": "low", "stylist": "low"}
    assert len(summary["runs"]) == 2 and summary["aggregate"]["n_runs"] == 2

    for i, run_summary in enumerate(summary["runs"], start=1):
        result, play = results[i], plays[i]
        assert run_summary["run_id"] == result["run_id"]
        assert run_summary["wall_time_s"] == result["wall_time_s"]
        assert run_summary["elapsed_ms"] == result["elapsed_ms"]
        assert run_summary["status"] == result["status"] == "proposed"
        assert run_summary["source"] == result["source"] == "scripted_stub"
        assert run_summary["planner_source"] == "model"
        assert run_summary["propose_play_attempts"] == 1
        assert run_summary["rejections"] == []
        assert run_summary["passed_first_try"] is True
        assert run_summary["passed_after_revision"] is False
        assert run_summary["fell_back"] is False
        assert run_summary["winning_play_shape"]["mechanic"] == play["mechanic"]
        assert run_summary["winning_play_shape"]["expected_outcome"]["units"] == play["expected_outcome"]["units"]
        # the stub backend never sets usage_metadata (agents/planner/stub_llm.py) -- both must be
        # consistently empty, not silently defaulted somewhere else in the pipeline.
        assert run_summary["token_totals"] == {}
        assert run_summary["model_calls"] == 0

    mn, med, mx = (summary["aggregate"]["wall_time_s"][k] for k in ("min", "median", "max"))
    assert mn is not None and mn <= med <= mx
    assert summary["aggregate"]["status_counts"] == {"proposed": 2}
    assert summary["aggregate"]["source_counts"] == {"scripted_stub": 2}
    assert summary["aggregate"]["passed_first_try_count"] == 2
    assert summary["aggregate"]["fell_back_count"] == 0
