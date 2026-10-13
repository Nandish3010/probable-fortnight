"""POST /approve on the recorded Tea play: bounded local wall time, the copy branch hard-capped,
and the big tables no longer parsed in full. Live, Approve took 7 to 15 s: the local work (about
1.5 s on a laptop, several times that on a Cloud Run vCPU) ran in front of the BigQuery copy call,
and that call's "6 s" timeout was only a per-request bound (see jobs/sense/copy.py)."""
from __future__ import annotations

import json
import time
from datetime import UTC, date, datetime

import pytest

from agents.gate.config import load_tenant
from agents.gate.store import LocalStore
from jobs.sense import forecast as forecast_mod
from services.api import approve as approve_mod
from services.api.approve import approve

TEA = "play_tea_ds04_v1"


@pytest.fixture
def now_asof(data_dir):
    as_of_str = json.loads((data_dir / "manifest.json").read_text())["as_of"]
    return datetime.fromisoformat(f"{as_of_str}T03:30:00+00:00").astimezone(UTC), date.fromisoformat(as_of_str)


@pytest.fixture
def vertex_cfg(monkeypatch):
    monkeypatch.setenv("TAAL_FAKE_PROJECT", "fake-project")
    monkeypatch.setattr(approve_mod, "load_models", lambda: {"backend": "vertex", "vertex": {"project_env": "TAAL_FAKE_PROJECT", "location": "fake-region"}, "ids": {"flash": "fake-model"}})


def _without_copy(store, play_id):
    """Reset a seeded play to "no copy yet", so the test exercises the approve-time copy path even
    when the play was seeded with committed pre-generated BigQuery copy (fixtures/copy_pregenerated.json)."""
    row = store.find("plays", play_id=play_id)[-1]
    play = json.loads(row["play_json"])
    play["copy"]["variants"], play["copy"]["copy_status"] = [], "pending"
    approve_mod._save_play(store, row, play)


def test_tea_approve_local_wall_time_is_bounded(sandbox, now_asof):
    now, as_of = now_asof
    t0 = time.perf_counter()
    resp = approve(sandbox, load_tenant(), TEA, now, as_of=as_of)
    wall = time.perf_counter() - t0
    print(f"\nlocal approve of {TEA}: {wall:.3f}s (was about 1.5s before the change)")
    assert resp["status"] == "approved" and resp["offers_written"] == resp["assignment"]["treated_n"] > 0
    # generous for slow CI; the pre-change path was 3x this on a laptop, ~7 to 15 s live
    assert wall < 2.5, f"local approve work took {wall:.2f}s"


def test_approve_never_parses_the_whole_sales_or_forecast_tables(sandbox, now_asof, monkeypatch):
    now, as_of = now_asof
    full_reads: list[str] = []
    real = LocalStore.read

    def spy(self, table):
        full_reads.append(table)
        return real(self, table)

    monkeypatch.setattr(LocalStore, "read", spy)
    approve(sandbox, load_tenant(), TEA, now, as_of=as_of)
    assert "sales_daily" not in full_reads and "forecasts" not in full_reads, full_reads


def test_a_hung_bigquery_copy_is_cut_at_the_budget_and_templates_are_used(sandbox, now_asof, vertex_cfg, monkeypatch):
    now, as_of = now_asof
    monkeypatch.setattr(approve_mod, "COPY_BUDGET_S", 0.4)

    def hung(*a, **k):
        time.sleep(2.0)
        return []

    monkeypatch.setattr(approve_mod, "generate_copy_bigquery", hung)
    _without_copy(sandbox, TEA)
    t0 = time.perf_counter()
    resp = approve(sandbox, load_tenant(), TEA, now, as_of=as_of)
    wall = time.perf_counter() - t0
    assert wall < 1.8, f"approve waited for the hung copy call: {wall:.2f}s"
    assert resp["copy"]["variants"] > 0 and resp["offers_written"] > 0


def test_copy_call_starts_before_the_local_work_and_overlaps_it(sandbox, now_asof, vertex_cfg, monkeypatch):
    now, as_of = now_asof
    stamps: dict[str, float] = {}

    def copy_fake(*a, **k):
        stamps["copy_start"] = time.perf_counter()
        time.sleep(0.5)
        return []

    real_forecast = approve_mod.forecast

    def forecast_spy(*a, **k):
        stamps["forecast_start"] = time.perf_counter()
        return real_forecast(*a, **k)

    monkeypatch.setattr(approve_mod, "generate_copy_bigquery", copy_fake)
    monkeypatch.setattr(approve_mod, "forecast", forecast_spy)
    _without_copy(sandbox, TEA)
    t0 = time.perf_counter()
    approve(sandbox, load_tenant(), TEA, now, as_of=as_of)
    wall = time.perf_counter() - t0
    assert stamps["copy_start"] < stamps["forecast_start"]
    assert wall < 0.5 + 0.9, f"copy (0.5 s) should hide behind the local work, not add to it: {wall:.2f}s"


def test_forecast_for_one_sku_equals_the_full_run_filtered_to_it(base_store):
    sku = base_store.find("plays", play_id=TEA)
    sku = json.loads(sku[-1]["play_json"])["target"]["sku"]
    as_of = date.fromisoformat(json.loads((base_store.root / "manifest.json").read_text())["as_of"])
    one = forecast_mod.forecast(base_store, as_of, "t", skus=[sku], includes_plays=True)
    full = [r for r in forecast_mod.forecast(base_store, as_of, "t", includes_plays=True) if r["sku"] == sku]
    assert one and one == full


def test_read_where_and_max_str_match_a_full_read(base_store):
    rows = base_store.read("sales_daily")
    sku = rows[0]["sku"]
    assert base_store.read_where("sales_daily", "sku", [sku]) == [r for r in rows if r["sku"] == sku]
    assert base_store.read_where("sales_daily", "sku", ["NO-SUCH-SKU"]) == []
    assert base_store.max_str("sales_daily", "date") == max(r["date"] for r in rows)


def test_two_plays_on_one_sku_leave_one_play_forecast_set(sandbox, now_asof):
    """The second approve for a SKU takes the rewrite path; the file must not keep both runs."""
    now, as_of = now_asof
    pids = ["play_cola_ds07_v1", "play_cola_ds02_v1"]
    skus = {json.loads(sandbox.find("plays", play_id=p)[-1]["play_json"])["target"]["sku"] for p in pids}
    assert len(skus) == 1, "fixture assumption: both cola plays target the same SKU"
    for p in pids:
        approve(sandbox, load_tenant(), p, now, as_of=as_of)
    sku = skus.pop()
    mine = [r for r in sandbox.read("forecasts") if r["sku"] == sku and r.get("includes_plays")]
    assert mine and len({r["run_id"] for r in mine}) == 1 and mine[0]["run_id"].startswith("refc_play_cola_ds02_v1")


def _with_existing_copy(store, play_id):
    from agents.gate.store import load_catalogue
    from jobs.sense.copy import generate_copy

    row = store.find("plays", play_id=play_id)[-1]
    play = json.loads(row["play_json"])
    gap = store.find("gaps", gap_id=play["gap_id"])[-1]
    product = load_catalogue(store)[play["target"]["sku"]]
    play["copy"]["variants"] = generate_copy(play, product, None, gap["evidence"].get("expiry_date"), play["copy"]["language_set"])
    assert play["copy"]["variants"]
    approve_mod._save_play(store, row, play)
    return play["copy"]["variants"]


def test_play_with_existing_copy_makes_no_bigquery_call_and_keeps_the_response_shape(sandbox, now_asof, vertex_cfg, monkeypatch):
    now, as_of = now_asof
    calls: list[int] = []

    def forbidden(*a, **k):
        calls.append(1)
        raise AssertionError("BigQuery copy must not be called for a play that already has copy")

    monkeypatch.setattr(approve_mod, "generate_copy_bigquery", lambda *a, **k: [])
    _without_copy(sandbox, TEA)
    base = approve(sandbox, load_tenant(), TEA, now, as_of=as_of)  # no BigQuery rows -> templated path
    assert base["copy"]["source"] == "templated"
    existing = _with_existing_copy(sandbox, "play_chips_ds07_v1")
    monkeypatch.setattr(approve_mod, "generate_copy_bigquery", forbidden)
    resp = approve(sandbox, load_tenant(), "play_chips_ds07_v1", now, as_of=as_of)
    assert calls == []
    assert resp["copy"]["source"] == "existing" and resp["copy"]["variants"] == len(existing) and resp["copy"]["rejected"] == []
    assert set(base) == set(resp) and set(base["copy"]) == set(resp["copy"])
    assert resp["offers_written"] == resp["assignment"]["treated_n"] > 0
    texts = {o["text"] for o in sandbox.find("offers", play_id="play_chips_ds07_v1")}
    assert texts <= {v["text"] for v in existing}
