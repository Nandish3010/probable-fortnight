"""Pre-generated BigQuery copy: the committed fixture (fixtures/copy_pregenerated.json) is loaded
onto the seeded plays, approve reuses it with no BigQuery call, and the response says honestly
where the copy came from. No cloud call is made: BigQuery is faked."""
from __future__ import annotations

import json
import shutil
import time
from datetime import UTC, date, datetime

import pytest

from agents.gate.config import load_tenant
from agents.gate.store import load_catalogue
from harness import pregenerate_copy as pre
from harness.seed_plays import _apply_pregenerated_copy
from jobs.sense import copy_pregenerated as cp
from jobs.sense.copy import generate_copy, validate_copy
from services.api import approve as approve_mod
from services.api.approve import approve

PLAY_ID = "play_tea_ds04_v1"


def _play_and_best_before(store, play_id=PLAY_ID):
    row = store.find("plays", play_id=play_id)[-1]
    play = json.loads(row["play_json"])
    gap = store.find("gaps", gap_id=play["gap_id"])[-1]
    return row, play, gap["evidence"].get("expiry_date")


def _synthetic_entry(store, play, best_before):
    """Stand-in for BigQuery output: the templated text with a marker, one distinct line per slot
    (the real fixture is written only by harness/pregenerate_copy.py from a live call)."""
    base = generate_copy(play, load_catalogue(store)[play["target"]["sku"]], None, best_before, play["copy"]["language_set"])
    variants = [{**v, "text": f"({'abcdefgh'[i]}) {v['text']}"} for i, v in enumerate(base)]
    return {"model": "fake-model", "location": "fake-region", "method": cp.METHOD, "fingerprint": cp.fingerprint(play, best_before), "variants": variants}


@pytest.fixture
def fixture_file(tmp_path, monkeypatch):
    path = tmp_path / "copy_pregenerated.json"
    monkeypatch.setattr(cp, "FIXTURE_PATH", path)
    cp.clear_cache()
    yield path
    cp.clear_cache()


def test_committed_fixture_is_well_formed_and_loaded_onto_the_seeded_plays(base_store):
    """Every entry is self-describing, validates, and is what `make generate` put on the seeded play."""
    cp.clear_cache()
    fixture = cp.load_fixture(cp.FIXTURE_PATH)
    assert fixture, "fixtures/copy_pregenerated.json is missing or empty"
    for play_id, entry in fixture.items():
        assert {"generated_at", "model", "location", "method", "fingerprint", "variants"} <= set(entry)
        assert entry["method"] == cp.METHOD and entry["model"] and entry["location"]
        _, play, best_before = _play_and_best_before(base_store, play_id)
        assert entry["fingerprint"] == cp.fingerprint(play, best_before), f"{play_id}: fixture is stale for the seeded play"
        accepted, reasons = validate_copy(entry["variants"], play, best_before)
        assert reasons == [] and len(accepted) == len(entry["variants"])
        # the seed put exactly these variants on the play
        assert play["copy"]["variants"] == entry["variants"] and play["copy"]["copy_status"] == "generated"
        # one distinct line per slot within a language
        for lang in play["copy"]["language_set"]:
            texts = [v["text"] for v in entry["variants"] if v["language"] == lang]
            assert len(set(texts)) == len(texts)
    assert {"play_tea_ds04_v1", "play_chips_ds07_v1"} <= set(fixture)


def test_pregenerated_variants_only_for_a_matching_valid_entry(sandbox, fixture_file):
    _, play, best_before = _play_and_best_before(sandbox)
    entry = _synthetic_entry(sandbox, play, best_before)
    fixture_file.write_text(json.dumps({PLAY_ID: entry}), encoding="utf-8")
    assert cp.pregenerated_variants(play, best_before) == entry["variants"]
    # no entry for another play
    other = dict(play, play_id="play_other")
    assert cp.pregenerated_variants(other, best_before) is None
    # the play changed since generation (different mechanic parameters) -> entry no longer applies
    changed = json.loads(json.dumps(play))
    changed["mechanic_params"] = {**(changed.get("mechanic_params") or {}), "discount_pct": 99}
    assert cp.pregenerated_variants(changed, best_before) is None
    # a variant that fails the validator (best-before missing) -> not used
    bad = json.loads(json.dumps(entry))
    bad["variants"][0]["text"], bad["variants"][0]["disclosure_included"] = "Tea is here.", False
    fixture_file.write_text(json.dumps({PLAY_ID: bad}), encoding="utf-8")
    cp.clear_cache()
    assert cp.pregenerated_variants(play, best_before) is None


def test_seed_loads_the_fixture_onto_the_matching_play_and_leaves_others_templated(data_dir, tmp_path, fixture_file):
    work = tmp_path / "tenant"
    work.mkdir()
    for table in ("gaps.jsonl", "plays.jsonl", "products.jsonl"):
        shutil.copy(data_dir / table, work / table)
    from agents.gate.store import LocalStore

    store = LocalStore(work)
    row, play, best_before = _play_and_best_before(store)
    play["copy"]["variants"], play["copy"]["copy_status"] = [], "pending"
    entry = _synthetic_entry(store, play, best_before)
    fixture_file.write_text(json.dumps({PLAY_ID: entry}), encoding="utf-8")
    _apply_pregenerated_copy(str(work), {"play": play})
    stored = json.loads(store.find("plays", play_id=PLAY_ID)[-1]["play_json"])
    assert stored["copy"]["variants"] == entry["variants"] and stored["copy"]["copy_status"] == "generated"
    # a play with no fixture entry is untouched
    cola = json.loads(store.find("plays", play_id="play_cola_ds07_v1")[-1]["play_json"])
    cola["copy"]["variants"], cola["copy"]["copy_status"] = [], "pending"
    store.upsert("plays", "play_id", {**store.find("plays", play_id="play_cola_ds07_v1")[-1], "play_json": json.dumps(cola)})
    _apply_pregenerated_copy(str(work), {"play": cola})
    assert json.loads(store.find("plays", play_id="play_cola_ds07_v1")[-1]["play_json"])["copy"]["variants"] == []


@pytest.fixture
def vertex_cfg(monkeypatch):
    monkeypatch.setenv("TAAL_FAKE_PROJECT", "fake-project")
    monkeypatch.setattr(approve_mod, "load_models", lambda: {"backend": "vertex", "vertex": {"project_env": "TAAL_FAKE_PROJECT", "location": "fake-region"}, "ids": {"flash": "fake-model"}})


@pytest.fixture
def now_asof(data_dir):
    as_of_str = json.loads((data_dir / "manifest.json").read_text())["as_of"]
    return datetime.fromisoformat(f"{as_of_str}T03:30:00+00:00").astimezone(UTC), date.fromisoformat(as_of_str)


def _store_variants(store, variants, status="generated"):
    row, play, best_before = _play_and_best_before(store)
    play["copy"]["variants"], play["copy"]["copy_status"] = variants, status
    approve_mod._save_play(store, row, play)
    return play, best_before


def test_approve_with_pregenerated_copy_makes_no_bigquery_call_and_reports_provenance(sandbox, now_asof, vertex_cfg, fixture_file, monkeypatch):
    now, as_of = now_asof
    _, play, best_before = _play_and_best_before(sandbox)
    entry = _synthetic_entry(sandbox, play, best_before)
    fixture_file.write_text(json.dumps({PLAY_ID: entry}), encoding="utf-8")
    _store_variants(sandbox, entry["variants"])
    calls: list[int] = []

    def forbidden(*a, **k):
        calls.append(1)
        raise AssertionError("approve must not call BigQuery for a play with pre-generated copy")

    monkeypatch.setattr(approve_mod, "generate_copy_bigquery", forbidden)
    t0 = time.perf_counter()
    resp = approve(sandbox, load_tenant(), PLAY_ID, now, as_of=as_of)
    wall = time.perf_counter() - t0
    assert calls == []
    assert resp["copy"]["source"] == "existing" and resp["copy"]["provenance"] == cp.PROVENANCE
    assert resp["copy"]["variants"] == len(entry["variants"]) and resp["copy"]["rejected"] == []
    assert wall < approve_mod.COPY_BUDGET_S, f"approve took {wall:.2f}s; with stored copy it needs no copy budget"
    # the offers carry the stored, pre-generated text and nothing else
    texts = {o["text"] for o in sandbox.find("offers", play_id=PLAY_ID)}
    assert texts and texts <= {v["text"] for v in entry["variants"]}
    assert resp["offers_written"] == resp["assignment"]["treated_n"] > 0


def test_provenance_is_not_claimed_for_copy_that_is_not_the_stored_bigquery_output(sandbox, now_asof, vertex_cfg, fixture_file, monkeypatch):
    now, as_of = now_asof
    _, play, best_before = _play_and_best_before(sandbox)
    entry = _synthetic_entry(sandbox, play, best_before)
    fixture_file.write_text(json.dumps({PLAY_ID: entry}), encoding="utf-8")
    # the play carries valid copy, but not the fixture's text (a recorded or hand-edited play)
    other = generate_copy(play, load_catalogue(sandbox)[play["target"]["sku"]], None, best_before, play["copy"]["language_set"])
    _store_variants(sandbox, other)
    monkeypatch.setattr(approve_mod, "generate_copy_bigquery", lambda *a, **k: pytest.fail("no BigQuery call expected"))
    resp = approve(sandbox, load_tenant(), PLAY_ID, now, as_of=as_of)
    assert resp["copy"]["source"] == "existing" and resp["copy"]["provenance"] == "existing"


def test_a_play_without_copy_still_takes_the_budgeted_path_and_says_templated(sandbox, now_asof, vertex_cfg, fixture_file, monkeypatch):
    now, as_of = now_asof
    _store_variants(sandbox, [], "pending")
    monkeypatch.setattr(approve_mod, "generate_copy_bigquery", lambda *a, **k: [])
    resp = approve(sandbox, load_tenant(), PLAY_ID, now, as_of=as_of)
    assert resp["copy"]["source"] == "templated" and resp["copy"]["provenance"] == "templated"


def test_generation_checks_reject_invented_numbers_duplicates_and_missing_slots(sandbox):
    _, play, best_before = _play_and_best_before(sandbox)
    cat = load_catalogue(sandbox)
    product = cat[play["target"]["sku"]]
    good = [{**v, "text": f"({'abcdefgh'[i]}) {v['text']}"} for i, v in enumerate(generate_copy(play, product, None, best_before, play["copy"]["language_set"]))]
    assert pre.check_variants(good, play, best_before, product, None) == []
    invented = [dict(v) for v in good]
    invented[0]["text"] += " Only 7 left."
    assert any("numbers not in" in p for p in pre.check_variants(invented, play, best_before, product, None))
    dup = [dict(v) for v in good]
    dup[1]["text"] = dup[0]["text"]
    assert any("duplicate" in p for p in pre.check_variants(dup, play, best_before, product, None))
    assert any("slots" in p for p in pre.check_variants(good[:-1], play, best_before, product, None))


def test_bigquery_prompts_differ_per_segment_and_keep_their_angle_on_a_partial_retry(sandbox, monkeypatch):
    """The model is near-deterministic for an identical prompt, so each segment gets its own angle;
    a retry for a subset of segments passes angle_order so the angles do not shift."""
    from jobs.sense import copy as copy_mod

    seen: list[dict[str, str]] = []

    class FakeJob:
        def result(self, **k):
            return []

    class FakeClient:
        def query(self, sql, job_config=None, **k):
            rows = job_config.query_parameters[0].values
            seen.append({r.struct_values["segment_id"]: r.struct_values["prompt"] for r in rows})
            return FakeJob()

    monkeypatch.setattr(copy_mod, "_bq_client", lambda project, region: FakeClient())
    _, play, best_before = _play_and_best_before(sandbox)
    product = load_catalogue(sandbox)[play["target"]["sku"]]
    segs = play["audience"]["segment_ids"]
    copy_mod.generate_copy_bigquery(play, product, best_before, ["en"], "p", "r", "m")
    full = seen[-1]
    assert len(set(full.values())) == len(segs)
    assert not any(ch.isdigit() for angle in copy_mod.SEGMENT_ANGLES for ch in angle)
    subset = json.loads(json.dumps(play))
    subset["audience"]["segment_ids"] = [segs[3]]
    copy_mod.generate_copy_bigquery(subset, product, best_before, ["en"], "p", "r", "m", angle_order=segs)
    assert seen[-1][segs[3]] == full[segs[3]]


def test_prompt_states_the_offer_and_the_partner_and_forbids_made_up_claims():
    from jobs.sense.copy import _bq_prompt_text

    bundle = _bq_prompt_text("Masala Chips 200G", "bundle", None, 50.0, "2026-10-15", "en", "Lead with the offer itself.", "Cola Classic 250ML")
    assert "Masala Chips 200G and Cola Classic 250ML bought together for ₹50" in bundle and "2026-10-15" in bundle
    tea = _bq_prompt_text("Darjeeling Tea 100G", "transfer_plus_nudge", None, None, "2026-11-20", "en")
    assert "nearest Kutumb Mart outlet" in tea and "Nothing is free" in tea and "never mention a cart" in tea
    assert "10% off Quinoa 500G in store" in _bq_prompt_text("Quinoa 500G", "outlet_markdown", 10.0, None, None, "en")


def test_generation_checks_reject_claims_the_offer_does_not_make(sandbox):
    _, play, best_before = _play_and_best_before(sandbox)
    product = load_catalogue(sandbox)[play["target"]["sku"]]
    good = [{**v, "text": f"({'abcdefgh'[i]}) {v['text']}"} for i, v in enumerate(generate_copy(play, product, None, best_before, play["copy"]["language_set"]))]
    for claim in ("Get a free tea with your next transfer.", "We moved it to your cart."):
        bad = [dict(v) for v in good]
        bad[0]["text"] = f"{claim} Best before {best_before}."
        assert any("claims the offer does not make" in p for p in pre.check_variants(bad, play, best_before, product, None))
    bundle = {**play, "mechanic": "bundle", "mechanic_params": {"bundle_sku": "X", "bundle_price": 50}}
    v = {"segment_id": "seg_1", "language": "en", "text": f"Masala chips bundle for Rs 50. Best before {best_before}.", "disclosure_included": True}
    assert any("does not name the partner" in p for p in pre.slot_problems(v, bundle, best_before, product, {"name": "Cola Classic 250ML"}))
    v["text"] = f"Masala chips with Cola Classic 250ML for Rs 50. Best before {best_before}."
    assert pre.slot_problems(v, bundle, best_before, product, {"name": "Cola Classic 250ML"}) == []
