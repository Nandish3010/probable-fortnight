"""A live model names the play's identifier `id` instead of `play_id` (every recorded Tea run did, on
attempt 1): propose_play accepts the alias and drops the duplicate instead of rejecting the play."""
import json
from pathlib import Path
from types import SimpleNamespace

from agents.planner import tools as pt
from agents.planner.context import reset_context, set_context
from tests.agents.test_holdout_seed import _context

ROOT = Path(__file__).resolve().parents[2]


def _propose(sandbox, play):
    tok = set_context(_context(sandbox))
    try:
        return pt.propose_play(play, SimpleNamespace(state={}, actions=SimpleNamespace(escalate=False)))
    finally:
        reset_context(tok)


def _fixture():
    # a play the committed recording validated against this tenant, so only the id handling is in question
    return json.loads((ROOT / "eval" / "raw" / "planner_real_traces_tea_2026-10-12" / "run_02" / "play.json").read_text(encoding="utf-8"))


def test_top_level_id_is_accepted_as_play_id_and_dropped(sandbox):
    play = _fixture()
    play["id"] = play.pop("play_id")
    resp = _propose(sandbox, play)
    assert resp["valid"] is True and resp["errors"] == []
    assert "id" not in play and play["play_id"] == resp["play_id"]


def test_an_existing_play_id_wins_over_a_stray_id(sandbox):
    play = _fixture()
    want = play["play_id"]
    play["id"] = "something-else"
    resp = _propose(sandbox, play)
    assert resp["valid"] is True and play["play_id"] == want and "id" not in play


def test_a_play_with_neither_is_still_rejected(sandbox):
    play = _fixture()
    play.pop("play_id")
    resp = _propose(sandbox, play)
    assert resp["valid"] is False and any("play_id" in e for e in resp["errors"])
