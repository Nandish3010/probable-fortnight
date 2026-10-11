"""POST /approve runs the BigQuery offer-copy call and the local seasonal re-forecast concurrently
(services/api/approve.py). Fakes stand in for both so no cloud call is made."""
from __future__ import annotations

import json
import time
from datetime import UTC, datetime

import pytest

from agents.gate.config import load_tenant
from services.api import approve as approve_mod
from services.api.approve import approve

PLAY_ID = "play_chips_ds07_v1"
SLEEP_S = 0.3


@pytest.fixture
def run(sandbox, data_dir, monkeypatch):
    """Returns a callable that approves the flagship play on a fresh sandbox with a vertex-style
    config, and records which fakes were invoked."""
    calls: dict[str, list] = {"copy": [], "forecast": []}
    as_of_str = json.loads((data_dir / "manifest.json").read_text())["as_of"]
    now = datetime.fromisoformat(f"{as_of_str}T03:30:00+00:00").astimezone(UTC)
    monkeypatch.setenv("TAAL_FAKE_PROJECT", "fake-project")
    monkeypatch.setattr(approve_mod, "load_models", lambda: {"backend": "vertex", "vertex": {"project_env": "TAAL_FAKE_PROJECT", "location": "fake-region"}, "ids": {"flash": "fake-model"}})

    def go(copy_fake=None, forecast_fake=None):
        monkeypatch.setattr(approve_mod, "generate_copy_bigquery", copy_fake or (lambda *a, **k: calls["copy"].append(time.perf_counter()) or []))
        if forecast_fake is not None:
            monkeypatch.setattr(approve_mod, "forecast", forecast_fake)
        else:
            real = approve_mod.forecast

            def spy(*a, **k):
                calls["forecast"].append(time.perf_counter())
                return real(*a, **k)

            monkeypatch.setattr(approve_mod, "forecast", spy)
        t0 = time.perf_counter()
        resp = approve(sandbox, load_tenant(), PLAY_ID, now, as_of=datetime.fromisoformat(as_of_str).date())
        return resp, time.perf_counter() - t0

    go.calls = calls
    go.store = sandbox
    return go


def test_both_branches_run_and_response_keeps_its_shape(run):
    resp, _ = run()
    assert len(run.calls["copy"]) == 1 and len(run.calls["forecast"]) == 1
    assert list(resp) == ["play_id", "status", "assignment", "offers_written", "regressor_rows_touched", "copy", "forecast", "source", "elapsed_ms"]
    assert list(resp["assignment"]) == ["treated_n", "holdout_n", "seed", "fraction", "eligible_n", "excluded_subscribers"]
    assert list(resp["forecast"]) == ["run_id", "model", "latency_ms", "series", "writeoff_before_inr", "writeoff_after_inr", "play_window"]
    assert resp["status"] == "approved" and resp["source"] == "live"
    # the holdout assignment happened and fed the offers
    assert resp["assignment"]["holdout_n"] >= 1
    assert resp["offers_written"] == resp["assignment"]["treated_n"] > 0
    assert resp["regressor_rows_touched"] > 0 and resp["forecast"]["series"]


def test_a_copy_failure_still_yields_templated_copy_and_a_completed_forecast(run):
    def boom(*a, **k):
        raise RuntimeError("AI.GENERATE_TABLE unavailable")

    resp, _ = run(copy_fake=boom)
    assert resp["copy"]["variants"] > 0 and resp["copy"]["rejected"] == []
    play = json.loads(run.store.find("plays", play_id=PLAY_ID)[-1]["play_json"])
    assert play["copy"]["copy_status"] == "validated" and play["copy"]["variants"]
    assert resp["offers_written"] > 0
    assert resp["forecast"]["series"] and resp["forecast"]["model"]
    assert resp["forecast"]["writeoff_after_inr"] <= resp["forecast"]["writeoff_before_inr"]


def test_a_forecast_failure_does_not_cancel_the_copy_branch(run):
    finished = []

    def slow_copy(*a, **k):
        time.sleep(SLEEP_S)
        finished.append("copy")
        return []

    def bad_forecast(*a, **k):
        raise ValueError("forecast broke")

    with pytest.raises(ValueError, match="forecast broke"):
        run(copy_fake=slow_copy, forecast_fake=bad_forecast)
    assert finished == ["copy"]


def test_wall_time_is_the_max_of_the_two_branches_not_the_sum(run):
    """Approve has about a second of fixed local work (reading and rewriting the sandbox tables),
    so the whole call cannot come in under 0.5 s whatever the branches do. The fakes therefore
    stamp their own start and end, and the assertion is on the span they cover together: two 0.3 s
    sleeps that overlap take about 0.3 s, and run back to back they would take 0.6 s."""
    stamps: dict[str, tuple[float, float]] = {}

    def timed(name, ret):
        def fake(*a, **k):
            t0 = time.perf_counter()
            time.sleep(SLEEP_S)
            stamps[name] = (t0, time.perf_counter())
            return ret

        return fake

    resp, wall = run(copy_fake=timed("copy", []), forecast_fake=timed("forecast", []))
    span = max(e for _, e in stamps.values()) - min(s for s, _ in stamps.values())
    print(f"\nbranch span {span:.3f}s (sequential would be {2 * SLEEP_S:.1f}s); whole approve {wall:.3f}s")
    assert resp["status"] == "approved" and set(stamps) == {"copy", "forecast"}
    assert SLEEP_S <= span < 0.5, f"expected about max(a, b)={SLEEP_S}s, not a + b={2 * SLEEP_S}s; got {span:.3f}s"
