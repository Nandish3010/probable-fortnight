"""harness/recorded_traces.py: discovery, validation, selection and seeding of a committed
real-Gemini planner recording.

Exercised against a throwaway recording built once per module with
harness/record_flagship_traces.py --allow-stub. In that tmp copy ONLY, and nowhere else, the
recording is relabelled (via `_relabel_as_vertex` below) to look like a genuine
backend="vertex"/source="live_gemini" recording -- summary.json, the run's own result.json and
play.json, the trace's own `kind: run_summary` record, AND a real-looking `usage` token count
planted on one trace record -- purely to exercise the selection code below the discovery filter.
This simulates a genuine recording for the selection code only; discover_candidates' real
backend/source/usage checks (all of them, across all four files) are exactly what keep an actual
stub recording (there is no other kind in this environment) from ever being eligible --
test_stub_labelled_run_and_stub_backend_are_never_eligible and the negative-relabelling tests below
prove that filter still bites when the relabelling is withheld or left incomplete. Nothing here is
committed.
"""
from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import pytest

from agents.gate.store import LocalStore
from harness import record_flagship_traces as rpt
from harness import recorded_traces as rt
from harness import seed_plays as sp

GAP_ID = "gap_tea_ds04"  # any non-flagship demo gap; the flagship itself is never touched here


def _copy_recording(base_out_dir: Path, dest_raw_root: Path) -> Path:
    dest = dest_raw_root / base_out_dir.name
    shutil.copytree(base_out_dir, dest)
    return dest


_FAKE_USAGE = {"prompt_token_count": 512, "candidates_token_count": 64, "total_token_count": 576}


def _relabel_summary_only(out_dir: Path, run_indices: tuple[int, ...] = (1, 2)) -> None:
    """The OLD (pre-hardening) relabelling: summary.json's directory-level "backend" and the
    given runs' own "source", and nothing else -- result.json, play.json and trace.jsonl are left
    exactly as the stub run wrote them. Used only by the negative test proving this alone is no
    longer enough to make a run eligible."""
    summary_path = out_dir / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["backend"] = "vertex"
    for i in run_indices:
        summary["runs"][i - 1]["source"] = "live_gemini"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")


def _relabel_as_vertex(out_dir: Path, run_indices: tuple[int, ...] = (1, 2), with_usage: bool = True) -> None:
    """Relabel a --allow-stub recording in EVERY place discover_candidates now checks, for the
    given run indices only -- the only way to exercise the selection code below the discovery
    filter without a real Vertex call (see the module docstring): summary.json (directory-level
    "backend", and the run's own "source"/"planner_source"), that run's own result.json
    ("source"/"planner_source") and play.json ("source"), and its trace.jsonl's own `kind:
    run_summary` record ("source"/"backend"/"model") -- plus, with `with_usage` (the default), a
    realistic non-empty `usage` block planted on one ordinary (non-summary) trace record, standing
    in for the usage_metadata a real Gemini call reports and the stub backend never does.
    `with_usage=False` leaves every label relabelled but no record carrying usage, for the
    negative test proving that signal alone still gates eligibility."""
    summary_path = out_dir / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["backend"] = "vertex"
    for i in run_indices:
        summary["runs"][i - 1]["source"] = "live_gemini"
        summary["runs"][i - 1]["planner_source"] = "model"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    for i in run_indices:
        run_dir = out_dir / f"run_{i:02d}"

        result_path = run_dir / "result.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        result["source"] = "live_gemini"
        result["planner_source"] = "model"
        result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

        play_path = run_dir / "play.json"
        play = json.loads(play_path.read_text(encoding="utf-8"))
        play["source"] = "live_gemini"
        play_path.write_text(json.dumps(play, indent=2, ensure_ascii=False), encoding="utf-8")

        trace_path = run_dir / "trace.jsonl"
        records = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        usage_planted = False
        for rec in records:
            if rec.get("kind") == "run_summary":
                rec["source"] = "live_gemini"
                rec["backend"] = "vertex"
                rec["model"] = "gemini-2.5-flash"
            elif with_usage and not usage_planted and rec.get("author") == "planner":
                rec["usage"] = dict(_FAKE_USAGE)
                usage_planted = True
        trace_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n", encoding="utf-8")


def _tamper_play(out_dir: Path, run_tag: str, mutate) -> None:
    play_path = out_dir / run_tag / "play.json"
    play = json.loads(play_path.read_text(encoding="utf-8"))
    mutate(play)
    play_path.write_text(json.dumps(play, indent=2, ensure_ascii=False), encoding="utf-8")


@pytest.fixture(scope="module")
def base_recording_out(tmp_path_factory, data_dir):
    """Two real (well, --allow-stub) runs, recorded once for every test in this module -- the
    expensive part. Each test that needs to mutate anything works on its own copy (_copy_recording)
    so tests never see each other's edits."""
    raw_root = tmp_path_factory.mktemp("base-raw")
    out_dir = raw_root / "planner_real_traces_2020-01-01"
    rc = rpt.main(["--gap", GAP_ID, "--runs", "2", "--out", str(out_dir), "--allow-stub", "--base-data", str(data_dir)])
    assert rc == 0
    return out_dir


# --------------------------------------------------------------------------------- discovery


def test_stub_labelled_run_and_stub_backend_are_never_eligible(tmp_path, base_recording_out):
    raw_root = tmp_path / "raw"
    out_dir = _copy_recording(base_recording_out, raw_root)

    # backend is still "stub" (nothing relabelled yet): nothing is eligible, whatever any
    # individual run's own "source" says.
    assert rt.discover_candidates(GAP_ID, raw_root) == []

    # relabel the directory to "vertex" but leave run_02's own source as "scripted_stub": only
    # run_01 becomes eligible.
    _relabel_as_vertex(out_dir, run_indices=(1,))
    candidates = rt.discover_candidates(GAP_ID, raw_root)
    assert [c.run_tag for c in candidates] == ["run_01"]


def test_discovery_ignores_a_different_gap(tmp_path, base_recording_out):
    raw_root = tmp_path / "raw"
    out_dir = _copy_recording(base_recording_out, raw_root)
    _relabel_as_vertex(out_dir)
    assert rt.discover_candidates("gap_chips_ds07", raw_root) == []


def test_relabelling_only_summary_json_leaves_the_run_ineligible(tmp_path, base_recording_out):
    """The exact gap this hardening closes: summary.json alone (its directory-level "backend" and
    a run's own "source") used to be enough to make a stub run seedable as recorded_gemini. With
    result.json, play.json, the trace's own run_summary and its usage all still stub-labelled,
    discover_candidates must reject every run in this directory."""
    raw_root = tmp_path / "raw"
    out_dir = _copy_recording(base_recording_out, raw_root)
    _relabel_summary_only(out_dir)
    assert rt.discover_candidates(GAP_ID, raw_root) == []


def test_relabelling_everything_but_usage_leaves_the_run_ineligible(tmp_path, base_recording_out):
    """summary.json, result.json, play.json and the trace's own run_summary record all agree
    "live_gemini"/"vertex"/a "gemini*" model -- but no trace record carries a real `usage` token
    count, which no stub-driven run can ever produce (the stub backend never sets
    usage_metadata). discover_candidates must still reject every run in this directory."""
    raw_root = tmp_path / "raw"
    out_dir = _copy_recording(base_recording_out, raw_root)
    _relabel_as_vertex(out_dir, with_usage=False)
    assert rt.discover_candidates(GAP_ID, raw_root) == []


# --------------------------------------------------------------------------------- selection


def test_select_best_picks_highest_margin_with_earliest_index_tiebreak(monkeypatch):
    """The selection rule in isolation (validate_recording stubbed out to always pass): highest
    expected_outcome.margin_inr wins; an exact tie goes to whichever candidate is earliest in the
    list discover_candidates would have produced (newest directory, then ascending run index)."""
    monkeypatch.setattr(rt, "validate_recording", lambda data_dir, rec: (True, []))

    def make(tag: str, margin: float) -> rt.Recording:
        return rt.Recording(dir=Path("unused"), run_tag=tag, summary={}, run_summary={}, result={}, play={"expected_outcome": {"margin_inr": margin}}, trace_text="")

    candidates = [make("run_01", 100.0), make("run_02", 250.0), make("run_03", 250.0)]
    best, failures = rt.select_best("unused-data-dir", GAP_ID, candidates)
    assert failures == {}
    assert best is not None and best.run_tag == "run_02", "highest margin (250) wins; of the tie, run_02 is earliest"


def test_discovery_and_selection_resolve_a_real_tie_to_the_earliest_run(tmp_path, base_recording_out, data_dir):
    """The two stub runs plan the same gap under the same policy, so they produce the identical
    play (same play_id, mechanic, margin_inr) -- a genuine tie end to end, resolved to run_01."""
    raw_root = tmp_path / "raw"
    out_dir = _copy_recording(base_recording_out, raw_root)
    _relabel_as_vertex(out_dir)

    candidates = rt.discover_candidates(GAP_ID, raw_root)
    assert len(candidates) == 2
    best, failures = rt.select_best(str(data_dir), GAP_ID, candidates)
    assert failures == {}, f"expected both candidates to validate; got {failures}"
    assert best is not None and best.run_tag == "run_01"


# --------------------------------------------------------------------------------- validation


def test_validation_rejects_tampered_expected_outcome_units(tmp_path, base_recording_out, data_dir):
    raw_root = tmp_path / "raw"
    out_dir = _copy_recording(base_recording_out, raw_root)
    _relabel_as_vertex(out_dir)
    _tamper_play(out_dir, "run_01", lambda p: p["expected_outcome"].__setitem__("units", p["expected_outcome"]["units"] + 1))

    tampered = next(c for c in rt.discover_candidates(GAP_ID, raw_root) if c.run_tag == "run_01")
    ok, reasons = rt.validate_recording(str(data_dir), tampered)
    assert not ok
    assert any("expected_outcome.units" in r for r in reasons), reasons


def test_validation_rejects_a_changed_guardrail_detail(tmp_path, base_recording_out, data_dir):
    raw_root = tmp_path / "raw"
    out_dir = _copy_recording(base_recording_out, raw_root)
    _relabel_as_vertex(out_dir)
    _tamper_play(out_dir, "run_02", lambda p: p["guardrails"].__setitem__(0, {**p["guardrails"][0], "detail": "a hand-edited, untrue detail string"}))

    tampered = next(c for c in rt.discover_candidates(GAP_ID, raw_root) if c.run_tag == "run_02")
    ok, reasons = rt.validate_recording(str(data_dir), tampered)
    assert not ok
    assert any("guardrail" in r.lower() for r in reasons), reasons


def test_valid_recording_passes(tmp_path, base_recording_out, data_dir):
    raw_root = tmp_path / "raw"
    out_dir = _copy_recording(base_recording_out, raw_root)
    _relabel_as_vertex(out_dir)
    candidates = rt.discover_candidates(GAP_ID, raw_root)
    for cand in candidates:
        ok, reasons = rt.validate_recording(str(data_dir), cand)
        assert ok, reasons


# ----------------------------------------------------------------------------------- seeding


def test_seeding_writes_the_recorded_play_and_trace_with_new_provenance_only(tmp_path, base_recording_out, data_dir):
    raw_root = tmp_path / "raw"
    out_dir = _copy_recording(base_recording_out, raw_root)
    _relabel_as_vertex(out_dir)

    seed_dir = tmp_path / "seed-target"
    shutil.copytree(data_dir, seed_dir)  # a throwaway copy: seeding writes to it, data_dir must stay untouched

    result, message = rt.seed_from_recording(str(seed_dir), GAP_ID, raw_root=raw_root)
    assert result is not None and "seeded from committed recording" in message

    recorded_play = json.loads((out_dir / "run_01" / "play.json").read_text(encoding="utf-8"))  # run_01 wins the tie
    assert result["play"] == {**recorded_play, "source": "recorded_gemini"}

    store = LocalStore(str(seed_dir))
    rows = store.find("plays", play_id=recorded_play["play_id"])
    assert len(rows) == 1, "the recording must replace the gap's existing stub play, not duplicate it"
    assert json.loads(rows[0]["play_json"]) == result["play"]

    recorded_trace = [json.loads(line) for line in (out_dir / "run_01" / "trace.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    seeded_trace = store.read_events(result["run_id"])
    assert len(seeded_trace) == len(recorded_trace)
    summaries_seen = 0
    for recorded_ev, seeded_ev in zip(recorded_trace, seeded_trace, strict=True):
        if recorded_ev.get("kind") == "run_summary":
            summaries_seen += 1
            assert seeded_ev["source"] == "recorded_gemini"
            assert seeded_ev["recorded_source"] == recorded_ev["source"]
            assert seeded_ev["recorded_at"] is not None
            assert seeded_ev["recorded_in"]
            provenance_keys = {"source", "recorded_source", "recorded_at", "recorded_in"}
            assert {k: v for k, v in seeded_ev.items() if k not in provenance_keys} == {k: v for k, v in recorded_ev.items() if k not in provenance_keys}
        else:
            assert seeded_ev == recorded_ev
    assert summaries_seen == 1

    # data_dir itself was never touched by any of the above
    assert not any(json.loads(line)["play_id"] == recorded_play["play_id"] and json.loads(line).get("source") == "recorded_gemini" for line in (data_dir / "plays.jsonl").read_text(encoding="utf-8").splitlines() if line.strip())


# ------------------------------------------------------------------------ harness/seed_plays.py


def test_seed_plays_falls_back_to_stub_with_no_recordings(tmp_path, data_dir, monkeypatch):
    """An empty raw root (monkeypatched in, not the real repo state -- see the real-committed-state
    test below for that) means seed_plays must fall back to the scripted stub for the flagship,
    exactly as it always does for every other gap."""
    empty_raw_root = tmp_path / "empty-raw"
    empty_raw_root.mkdir()
    monkeypatch.setattr(rt, "RAW_ROOT_DEFAULT", empty_raw_root)

    seed_dir = tmp_path / "seed-target"
    shutil.copytree(data_dir, seed_dir)
    outs = asyncio.run(sp.seed_plays(str(seed_dir)))

    by_gap = {o["play"]["gap_id"]: o["play"] for o in outs}
    assert by_gap[sp.FLAGSHIP_GAP]["source"] == "scripted_stub"
    assert all(p["source"] == "scripted_stub" for p in by_gap.values())


def test_real_committed_state_each_gap_source_iff_a_recording_validates(tmp_path, data_dir):
    """No monkeypatching: runs harness.seed_plays exactly as `make generate` and the Docker build
    do, against whatever is actually committed under eval/raw right now. Every demo gap with a
    committed recording that validates is seeded from it ("recorded_gemini"); every gap without
    one keeps the scripted stub. The independent discover+select check below decides what
    "expected" means per gap, rather than a fact hardcoded here."""
    seed_dir = tmp_path / "seed-target"
    shutil.copytree(data_dir, seed_dir)
    outs = asyncio.run(sp.seed_plays(str(seed_dir)))
    by_gap = {o["play"]["gap_id"]: o["play"] for o in outs}

    for gap_id in sp.DEMO_GAPS:
        candidates = rt.discover_candidates(gap_id)  # real default eval/raw
        best, _ = rt.select_best(str(data_dir), gap_id, candidates) if candidates else (None, {})
        assert by_gap[gap_id]["source"] == ("recorded_gemini" if best is not None else "scripted_stub"), gap_id


def test_seed_plays_uses_the_committed_tea_recording_and_stubs_the_rest(tmp_path, data_dir):
    """The hero beat's Tea play comes from the committed real-Gemini recording, with its
    provenance in the seeded trace (the UI's "Recorded from Gemini" badge reads it); gaps with no
    recording (cola, kaju, quinoa) keep the scripted stub."""
    seed_dir = tmp_path / "seed-target"
    shutil.copytree(data_dir, seed_dir)
    outs = asyncio.run(sp.seed_plays(str(seed_dir)))
    by_gap = {o["play"]["gap_id"]: o for o in outs}

    tea = by_gap["gap_tea_ds04"]
    assert tea["play"]["source"] == "recorded_gemini"
    assert tea["source"] == "recorded_gemini" and tea["planner_source"] == "model"
    assert tea["play"]["mechanic"] == "transfer_plus_nudge"
    run_summary = next(e for e in reversed(tea["events"]) if e.get("kind") == "run_summary")
    assert run_summary["source"] == "recorded_gemini" and run_summary["recorded_source"] == "live_gemini"
    assert run_summary["recorded_in"].startswith("eval/raw/planner_real_traces_tea_")
    assert str(run_summary["model"]).startswith("gemini")

    for gap_id in ("gap_cola_ds07", "gap_cola_ds02", "gap_kaju_ds01", "gap_kaju_ds03", "gap_quinoa_out02"):
        assert by_gap[gap_id]["play"]["source"] == "scripted_stub", gap_id


def test_a_seed_pin_overrides_the_default_choice_and_a_bad_pin_is_ignored(tmp_path, base_recording_out, data_dir):
    raw_root = tmp_path / "raw"
    out_dir = _copy_recording(base_recording_out, raw_root)
    _relabel_as_vertex(out_dir, run_indices=(1, 2))
    default_dir = tmp_path / "default"
    shutil.copytree(data_dir, default_dir)
    res, msg = rt.seed_from_recording(default_dir, GAP_ID, raw_root)
    assert res is not None and "pinned" not in msg

    (raw_root / "seed_pins.json").write_text(json.dumps({GAP_ID: f"{out_dir.name}/run_02"}), encoding="utf-8")
    assert rt.read_pins(raw_root) == {GAP_ID: f"{out_dir.name}/run_02"}
    pinned_dir = tmp_path / "pinned"
    shutil.copytree(data_dir, pinned_dir)
    res, msg = rt.seed_from_recording(pinned_dir, GAP_ID, raw_root)
    assert res is not None and f"{out_dir.name}/run_02" in msg and "pinned" in msg

    (raw_root / "seed_pins.json").write_text(json.dumps({GAP_ID: f"{out_dir.name}/run_99"}), encoding="utf-8")
    bad_dir = tmp_path / "bad"
    shutil.copytree(data_dir, bad_dir)
    res, msg = rt.seed_from_recording(bad_dir, GAP_ID, raw_root)
    assert res is not None and "not usable" in msg


def test_the_seeded_tea_hero_is_the_pinned_clean_recording_with_the_unchanged_numbers(tmp_path, data_dir):
    """The Desk's Tea exhibit: one propose_play attempt, no rejection, and a rationale that states
    the recovered figure and the beat over a blanket markdown. The play numbers are the hero numbers
    that README, deck and video quote (they must not move when the exhibit is re-recorded)."""
    seed_dir = tmp_path / "seed-target"
    shutil.copytree(data_dir, seed_dir)
    outs = asyncio.run(sp.seed_plays(str(seed_dir)))
    tea = next(o for o in outs if o["play"]["gap_id"] == "gap_tea_ds04")
    play = tea["play"]
    assert (play["expected_outcome"]["margin_inr"], play["counterfactuals"]["play_net_inr"], play["counterfactuals"]["blanket_markdown_inr"]) == (9191.29, -25828.71, 32015.18)
    assert (play["audience"]["size_after_consent"], play["mechanic_params"]["transfer_units"]) == (394, 103)
    assert round(play["counterfactuals"]["blanket_markdown_inr"] + play["counterfactuals"]["play_net_inr"]) == 6186
    assert "9191" in play["rationale"].replace(",", "") and "6186" in play["rationale"].replace(",", "")
    assert next(g for g in play["guardrails"] if g["rule"] == "cite_or_drop")["passed"]
    summary = next(e for e in reversed(tea["events"]) if e.get("kind") == "run_summary")
    assert summary["recorded_in"] == "eval/raw/planner_real_traces_tea_2026-10-12c"
    proposes = [e for e in tea["events"] if "propose_play" in str(e.get("function_response", ""))]
    assert len(proposes) == 1 and "'valid': True" in str(proposes[0]["function_response"]), "the exhibit trace shows one propose_play, accepted first time"
