"""harness/first_attempt_acceptance.py: the committed first-attempt figures are reproducible from the
committed eval output, and today's gate still rejects every first play the recorded
gemini-2.5-flash runs proposed, so the 12 Oct gain is not the gate getting looser."""
from __future__ import annotations

import json

from harness.first_attempt_acceptance import ROOT, acceptance, first_attempt, replay

COMMITTED = ROOT / "eval" / "raw" / "live_eval_2026-10-12" / "first_attempt.json"


def test_counts_reproduce_the_committed_file():
    committed = json.loads(COMMITTED.read_text(encoding="utf-8"))
    assert acceptance() == {k: v for k, v in committed.items() if not k.startswith("replay_")}


def test_first_attempt_needs_one_propose_and_a_play():
    assert first_attempt(["estimate_outcomes", "check_guardrails", "propose_play"], "DONE play_x_v1")
    assert not first_attempt(["estimate_outcomes", "propose_play", "propose_play"], "DONE play_x_v1")
    assert not first_attempt(["estimate_outcomes", "propose_play"], "")


def test_todays_gate_still_rejects_every_recorded_first_attempt(data_dir):
    runs = replay(data_dir)
    assert len(runs) == 5
    assert all(not r["recorded_valid"][0] and not r["today"][0]["valid"] for r in runs)
