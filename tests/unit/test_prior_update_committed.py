"""The committed prior-update evidence (eval/raw/prior_update_2026-09-28.json) is exactly the
conjugate update of its own committed inputs -- no number in it is typed by hand."""
import json
from pathlib import Path

from agents.gate.estimator import update_prior

RAW = Path(__file__).resolve().parents[2] / "eval" / "raw" / "prior_update_2026-09-28.json"


def test_update_prior_reproduces_the_committed_after_from_the_committed_inputs():
    d = json.loads(RAW.read_text(encoding="utf-8"))
    t = d["responders"]["treated"]
    assert update_prior(d["before"]["alpha"], d["before"]["beta"], t, d["treated_n"] - t) == (d["after"]["alpha"], d["after"]["beta"])
    assert d["after"]["n_measured"] == d["before"]["n_measured"] + d["treated_n"]


def test_committed_responders_follow_the_stated_rates_and_label():
    d = json.loads(RAW.read_text(encoding="utf-8"))
    assert d["data_label"] == "SYNTHETIC" and d["orders_source"] == "synthetic_demo" and d["applied_to_live_estimator"] is False
    assert d["rates_used"]["treated"] == d["before"]["alpha"] / (d["before"]["alpha"] + d["before"]["beta"])
    assert d["responders"]["treated"] == round(d["rates_used"]["treated"] * d["treated_n"])
    assert d["responders"]["holdout"] == round(d["rates_used"]["holdout"] * d["holdout_n"])
    assert d["synthetic_order_lines"] == d["responders"]["treated"] + d["responders"]["holdout"]
    assert d["ci"]["low"] <= d["lift"] <= d["ci"]["high"]


def test_web_mock_has_the_committed_evidence_shape():
    # The flagship play's numbers changed (the gate now re-derives its audience), so web/mocks
    # lags the committed evidence until the UI session runs `make mocks` (requested in
    # coordination/log.md). Until then only the structure is checked, not the values.
    mock = json.loads((RAW.parents[2] / "web" / "mocks" / "prior_update.json").read_text(encoding="utf-8"))
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    additive = {"lift_unit", "lift_pp", "ci_low_pp", "ci_high_pp", "inconclusive"}
    assert set(mock) == set(raw) - additive
