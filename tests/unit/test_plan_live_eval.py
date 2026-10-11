"""/health's additive plan_live_eval field: read from the committed evidence file, fail soft."""

import json

from services.api.plan_live_eval import SOURCE, load_plan_live_eval


def test_committed_file_loads():
    d = load_plan_live_eval()
    assert d is not None
    assert set(d) == {"date", "passed", "total", "p50_s", "source"}
    assert d["source"] == SOURCE
    assert 0 <= d["passed"] <= d["total"] and d["total"] >= 20 and d["p50_s"] > 0


def test_missing_file_omits(tmp_path):
    assert load_plan_live_eval(tmp_path) is None


def test_malformed_file_omits(tmp_path):
    (tmp_path / "eval/raw").mkdir(parents=True)
    f = tmp_path / SOURCE
    f.write_text("{not json")
    assert load_plan_live_eval(tmp_path) is None
    f.write_text(json.dumps({"date": "2026-10-11", "summary": {"passed": 1}}))
    assert load_plan_live_eval(tmp_path) is None
