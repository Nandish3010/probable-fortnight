"""Online Retail II loader rules, and the committed real-data backtest numbers reproduce from the
committed sample (no raw data needed)."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from data.external.online_retail_ii.load import keep_line, sample_to_tables, serial_to_date
from harness.external_backtest import run, synthetic_reference

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "data" / "external" / "online_retail_ii" / "sample"


def test_line_rules():
    assert keep_line("489434", "85048", 12, 6.95)
    assert keep_line("489434", "21232A", 1, 1.25)
    assert keep_line("C489449", "22087", -12, 2.95)   # cancellation, netted later
    assert not keep_line("C489449", "22087", 12, 2.95)  # cancellation must be negative
    assert not keep_line("489434", "22087", -1, 2.95)   # negative sale without a "C" invoice
    assert not keep_line("489434", "POST", 1, 18.0)     # postage is not a product
    assert not keep_line("489434", "85048", 1, 0.0)     # free / adjustment


def test_excel_serial_date():
    assert serial_to_date(40148.322916666664) == date(2009, 12, 1)


def test_absent_fields_stay_none():
    t = sample_to_tables(SAMPLE)
    assert t["inventory_batches"] == [] and t["inbound"] == []
    assert all(p["unit_cost"] is None and p["shelf_life_days"] is None and p["category"] == "unclassified" for p in t["products"])
    assert len(t["products"]) == 300


def test_committed_numbers_reproduce():
    committed = json.loads(max((ROOT / "eval" / "raw").glob("external_backtest_*.json")).read_text())
    now = run(SAMPLE, "check")
    for k in ("mean_mape", "wape", "mean_bias", "n_origins", "forecast_method_counts", "spread_behind_the_mean"):
        assert now[k] == committed[k]
    assert now["gap_detector"]["gaps_total"] == 0


def test_synthetic_reference_reproduces_both_metrics():
    committed = json.loads(max((ROOT / "eval" / "raw").glob("external_backtest_*.json")).read_text())["synthetic_reference"]
    now = synthetic_reference()
    assert (now["mean_mape"], now["wape"]) == (committed["mean_mape"], committed["wape"])
    assert now["mean_mape"] == committed["committed_2026-09-20"]["mean_mape"]  # tree still reproduces the 20 Sep MAPE
