"""Copy ahead of Approve (services/api/approve.py): the BigQuery AI.GENERATE_TABLE copy measures about
3-4 s, past Approve's 3 s budget, so it is also generated when a play is proposed or opened and
for the seeded plays at startup. Approve then takes the ready copy instead of racing the budget.
Fakes stand in for BigQuery; no cloud call is made."""
from __future__ import annotations

import json
import time
from datetime import UTC, datetime

import pytest

from agents.gate.config import load_tenant
from jobs.sense.copy import generate_copy
from services.api import approve as approve_mod
from services.api.approve import approve, schedule_copy_ahead, schedule_copy_ahead_for_store

TEA = "play_tea_ds04_v1"


@pytest.fixture(autouse=True)
def clean_cache():
    approve_mod._AHEAD.clear()
    approve_mod._AHEAD_FAILED.clear()
    yield
    for f in list(approve_mod._AHEAD.values()):
        f.result(timeout=5)
    approve_mod._AHEAD.clear()
    approve_mod._AHEAD_FAILED.clear()


@pytest.fixture
def now_asof(data_dir):
    as_of_str = json.loads((data_dir / "manifest.json").read_text())["as_of"]
    return datetime.fromisoformat(f"{as_of_str}T03:30:00+00:00").astimezone(UTC), as_of_str


@pytest.fixture
def vertex_cfg(monkeypatch):
    monkeypatch.setenv("TAAL_FAKE_PROJECT", "fake-project")
    monkeypatch.setattr(approve_mod, "load_models", lambda: {"backend": "vertex", "vertex": {"project_env": "TAAL_FAKE_PROJECT", "location": "fake-region"}, "ids": {"flash": "fake-model"}})


def _bq(calls: list, delay: float = 0.0):
    """A stand-in for generate_copy_bigquery that returns valid, recognisably non-templated copy."""

    def fake(play, product, best_before, languages, **k):
        calls.append(k.get("timeout_s"))
        time.sleep(delay)
        return [dict(v, text="Pick of the week: " + v["text"]) for v in generate_copy(play, product, None, best_before, languages)]

    return fake


def _forbidden(*a, **k):
    raise AssertionError("Approve must not start its own BigQuery copy call when copy is ready")


def _play(store, play_id):
    return json.loads(store.find("plays", play_id=play_id)[-1]["play_json"])


@pytest.fixture
def no_stored_copy(sandbox):
    """The seeded plays now carry pre-generated BigQuery copy (fixtures/copy_pregenerated.json) and
    Approve reuses it, so copy-ahead skips them. These tests are about plays proposed without
    stored copy, so strip the variants from the sandbox's plays."""
    for row in sandbox.read("plays"):
        play = json.loads(row["play_json"])
        play["copy"]["variants"] = []
        approve_mod._save_play(sandbox, row, play)


def _wait_all():
    for f in list(approve_mod._AHEAD.values()):
        f.result(timeout=5)


def test_seeded_plays_get_bigquery_copy_ahead_and_approve_uses_it(sandbox, no_stored_copy, now_asof, vertex_cfg, monkeypatch):
    now, as_of = now_asof
    calls: list = []
    monkeypatch.setattr(approve_mod, "generate_copy_bigquery", _bq(calls))
    started = schedule_copy_ahead_for_store(sandbox)
    assert started >= 2 and len(calls) <= started
    _wait_all()
    # the generous ahead-of-time timeout, not Approve's 3 s budget
    assert calls and all(t == approve_mod.COPY_AHEAD_TIMEOUT_S for t in calls)
    monkeypatch.setattr(approve_mod, "generate_copy_bigquery", _forbidden)
    resp = approve(sandbox, load_tenant(), TEA, now, as_of=datetime.fromisoformat(as_of).date())
    assert resp["copy"]["source"] == "bigquery" and resp["copy"]["rejected"] == []
    offers = sandbox.find("offers", play_id=TEA)
    assert offers and all(o["text"].startswith("Pick of the week: ") for o in offers)


def test_a_job_still_in_flight_is_awaited_not_duplicated(sandbox, no_stored_copy, now_asof, vertex_cfg, monkeypatch):
    now, as_of = now_asof
    calls: list = []
    monkeypatch.setattr(approve_mod, "generate_copy_bigquery", _bq(calls, delay=0.6))
    assert schedule_copy_ahead(sandbox, _play(sandbox, TEA))
    resp = approve(sandbox, load_tenant(), TEA, now, as_of=datetime.fromisoformat(as_of).date())
    assert len(calls) == 1 and resp["copy"]["source"] == "bigquery"


def test_scheduling_twice_starts_one_job(sandbox, no_stored_copy, vertex_cfg, monkeypatch):
    calls: list = []
    monkeypatch.setattr(approve_mod, "generate_copy_bigquery", _bq(calls, delay=0.2))
    play = _play(sandbox, TEA)
    assert schedule_copy_ahead(sandbox, play) and not schedule_copy_ahead(sandbox, play)
    _wait_all()
    assert len(calls) == 1


def test_changed_numbers_miss_the_ready_copy(sandbox, no_stored_copy, now_asof, vertex_cfg, monkeypatch):
    """Copy is keyed by what it is built from: a play whose mechanic numbers changed after the
    copy was generated must not ship the old numbers."""
    calls: list = []
    monkeypatch.setattr(approve_mod, "generate_copy_bigquery", _bq(calls))
    play = _play(sandbox, "play_chips_ds07_v1")
    schedule_copy_ahead(sandbox, play)
    _wait_all()
    product, partner, best_before = approve_mod._copy_inputs(sandbox, play)
    assert approve_mod._copy_ahead_future(play, product, partner, best_before) is not None
    changed = json.loads(json.dumps(play))
    changed["mechanic_params"] = dict(changed.get("mechanic_params") or {}, discount_pct=37)
    assert approve_mod._copy_ahead_future(changed, product, partner, best_before) is None


def test_a_failed_job_is_not_cached_and_approve_falls_back_to_its_own_call(sandbox, no_stored_copy, now_asof, vertex_cfg, monkeypatch):
    now, as_of = now_asof
    monkeypatch.setattr(approve_mod, "generate_copy_bigquery", lambda *a, **k: [])
    assert schedule_copy_ahead(sandbox, _play(sandbox, TEA))
    _wait_all()
    assert approve_mod._AHEAD == {}
    # and is not retried straight away
    assert not schedule_copy_ahead(sandbox, _play(sandbox, TEA))
    calls: list = []
    monkeypatch.setattr(approve_mod, "generate_copy_bigquery", _bq(calls))
    resp = approve(sandbox, load_tenant(), TEA, now, as_of=datetime.fromisoformat(as_of).date())
    assert len(calls) == 1 and resp["copy"]["source"] == "bigquery"


def test_off_on_the_stub_backend_and_by_flag(sandbox, vertex_cfg, monkeypatch):
    monkeypatch.setattr(approve_mod, "generate_copy_bigquery", _forbidden)
    monkeypatch.setenv("TAAL_COPY_AHEAD", "0")
    assert schedule_copy_ahead_for_store(sandbox) == 0
    monkeypatch.delenv("TAAL_COPY_AHEAD")
    monkeypatch.setattr(approve_mod, "load_models", lambda: {"backend": "stub"})
    assert schedule_copy_ahead_for_store(sandbox) == 0 and approve_mod._AHEAD == {}


def test_stored_copy_comes_first_then_copy_ahead(sandbox, now_asof, vertex_cfg, monkeypatch):
    """Order: valid copy already on the play (the pre-generated fixture) -> copy-ahead result ->
    one call inside Approve -> templates. A seeded play with stored copy is never sent to
    BigQuery: copy-ahead skips it and Approve reuses it."""
    now, as_of = now_asof
    monkeypatch.setattr(approve_mod, "generate_copy_bigquery", _forbidden)
    assert not schedule_copy_ahead(sandbox, _play(sandbox, TEA))
    resp = approve(sandbox, load_tenant(), TEA, now, as_of=datetime.fromisoformat(as_of).date())
    assert resp["copy"]["source"] == "existing" and resp["copy"]["provenance"] == "bigquery_pregenerated"
