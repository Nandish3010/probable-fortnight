from datetime import date

from agents.gate.store import LocalStore
from jobs.sense.forecast import HORIZON, forecast, series_for


def test_quantiles_ordered_and_full_horizon(base_store: LocalStore):
    rows = base_store.read("forecasts")
    per_series = {}
    for r in rows:
        assert r["p10"] <= r["p50"] <= r["p90"], r
        per_series.setdefault((r["sku"], r["node_id"]), set()).add(r["date"])
    assert all(len(d) == HORIZON for d in per_series.values())
    assert len(per_series) == 300 * 16


def test_regressors_cover_every_forecast_date(base_store: LocalStore):
    regs = {(r["date"], r["sku"], r["cluster_id"]) for r in base_store.read("future_regressors")}
    for r in base_store.read("forecasts"):
        assert (r["date"], r["sku"], r["cluster_id"]) in regs


def test_reforecast_with_play_changes_p50_only_inside_window(sandbox):
    as_of = date(2026, 9, 12)
    sku, nodes = "SKU-MASALA-CHIPS-200G", ["DS-07"]
    base = series_for([r for r in sandbox.read("forecasts") if r["sku"] == sku], sku, nodes)
    regs = sandbox.read("future_regressors")
    w0, w1 = "2026-09-14", "2026-09-18"
    for r in regs:
        if r["sku"] == sku and r["cluster_id"] == "south" and w0 <= r["date"] <= w1:
            r["on_promo"] = True
    sandbox.write("future_regressors", regs)
    new = series_for(forecast(sandbox, as_of, "test-refc", skus=[sku], includes_plays=True), sku, nodes)
    for d in base:
        if w0 <= d <= w1:
            assert new[d] > base[d], d
        else:
            assert abs(new[d] - base[d]) < 1e-6, d
