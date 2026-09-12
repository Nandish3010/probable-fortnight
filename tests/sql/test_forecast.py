from datetime import date, timedelta

from agents.gate.store import LocalStore
from jobs.sense.forecast import HORIZON, LEVEL_WINDOW, SeriesModel, forecast, series_for


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


def test_intermittent_series_uses_the_average_demand_rule():
    as_of = date(2026, 9, 12)
    # only 5 of the last 28 days (18%) have any recorded sale: well under the 50% threshold
    sale_days = [as_of - timedelta(days=n) for n in (1, 6, 12, 19, 26)]
    history = {d: (10.0, False) for d in sale_days}
    model = SeriesModel(history, as_of)
    assert model.is_intermittent
    expected_level = sum(u for u, _ in history.values()) / len(history)
    for i in range(HORIZON):
        d = as_of + timedelta(days=i)
        assert model.p50(d, on_promo=False, is_festival=False) == expected_level
        # promo has no effect on an intermittent series: there is too little signal to fit it
        assert model.p50(d, on_promo=True, is_festival=False) == expected_level


def test_regular_series_is_not_flagged_intermittent():
    as_of = date(2026, 9, 12)
    history = {as_of - timedelta(days=n): (10.0, False) for n in range(LEVEL_WINDOW)}
    model = SeriesModel(history, as_of)
    assert not model.is_intermittent


def test_forecast_labels_intermittent_rows_with_the_average_demand_method(sandbox):
    as_of = date(2026, 9, 12)
    sku = "SKU-QUINOA-500G"
    rows = forecast(sandbox, as_of, "test-intermittent", skus=[sku])
    methods = {r["method"] for r in rows}
    assert "average_demand_intermittent" in methods, "the planted quinoa slow mover should be sparse enough to trigger the rule"
