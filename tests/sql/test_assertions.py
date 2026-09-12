"""Every assertion under data/bigquery/assertions returns zero rows on the generated tenant after
Sense, and after an approve + measure cycle in a sandbox."""
from datetime import UTC, datetime

import pytest

from agents.gate.config import load_tenant
from data.bigquery.local import ASSERTIONS_DIR, build, run_all_assertions, run_assertion
from jobs.measure.run import run_measure
from services.api.approve import approve


@pytest.fixture(scope="module")
def con(base_store):
    return build(base_store)


def test_assertion_files_exist():
    names = {f.name for f in ASSERTIONS_DIR.glob("*.sql")}
    for n in ("sellby_le_expiry.sql", "gap_rupees_recompute.sql", "forecast_quantiles.sql", "consent_coverage.sql", "regressors_cover_forecast_dates.sql", "no_online_play_past_sellby.sql", "no_lift_without_holdout.sql", "holdout_fraction_min.sql"):
        assert n in names


def test_all_assertions_pass_on_base(con):
    for name, rows in run_all_assertions(con).items():
        assert rows == [], f"{name}: {rows[:3]}"


def test_assertions_pass_after_approve_and_measure(sandbox):
    approve(sandbox, load_tenant(), "play_chips_ds07_v1", datetime(2026, 9, 12, 9, 0, tzinfo=UTC))
    for t in ("plays", "play_assignments", "order_lines", "play_outcomes", "estimator_priors", "products"):
        sandbox._materialise(t)
    run_measure(sandbox.root, computed_at="2026-09-19T00:00:00Z")
    con = build(sandbox)
    assert con.execute("select count(*) from play_assignments").fetchone()[0] > 200
    for f in ASSERTIONS_DIR.glob("*.sql"):
        assert run_assertion(con, f) == [], f.name
