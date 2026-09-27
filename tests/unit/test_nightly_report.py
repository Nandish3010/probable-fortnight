"""harness/nightly_report.py with faked Cloud Run / Logging / BigQuery responses (no network)."""
from __future__ import annotations

import json

from harness import nightly_report as nr
from jobs.measure.run import NO_PLAYS_IN_BIGQUERY


def _ex(job, name, state, start="2026-09-28T20:00:05.123456789Z", end="2026-09-28T20:03:10Z", **kw):
    ex = {"name": f"projects/p/locations/r/jobs/{job}/executions/{name}", "createTime": start, "startTime": start,
          "completionTime": end, "conditions": [{"type": "Completed", "state": state}]}
    ex.update(kw)
    return ex


class FakeFetch:
    def __init__(self, executions, logs):
        self.executions, self.logs, self.calls = executions, logs, []

    def __call__(self, method, url, body):
        self.calls.append((method, url, body))
        if method == "GET":
            job = url.split("/jobs/")[1].split("/")[0]
            return {"executions": self.executions[job]}
        execution = body["filter"].split('execution_name"="')[1].rstrip('"')
        return {"entries": self.logs.get(execution, [])}


def fake_query(forecast_rows=25060):
    def query(sql, tenant_id):
        assert tenant_id == "kutumb-mart" and "@tenant_id" in sql
        if "FROM `amru-509214.taal.forecasts`" in sql:
            return [{"run_id": "sense_20260912_baseline_x", "model": "timesfm", "as_of": "2026-09-12", "rows_total": forecast_rows,
                     "cluster_rows": 25060, "node_rows": forecast_rows - 25060, "min_date": "2026-09-13", "max_date": "2026-10-10"}], 100
        if ".gaps`" in sql:
            return [{"type": "expiry_writeoff", "run_id": "r", "n": 400}, {"type": "rebalance", "run_id": "r", "n": 133}], 10
        if ".plays`" in sql:
            return [], 10
        if "sales_daily" in sql:
            return [{"max_date": "2026-09-12", "n": 324271}], 10
        return [{"n": 0}], 10
    return query


def _fakes(sense_states=("CONDITION_SUCCEEDED",) * 3, measure_log=None):
    execs = {
        "taal-sense": [_ex("taal-sense", f"taal-sense-{i}", s, start=f"2026-09-2{8 - i}T20:00:05Z", end=f"2026-09-2{8 - i}T20:04:05Z") for i, s in enumerate(sense_states)],
        "taal-measure": [_ex("taal-measure", "taal-measure-0", "CONDITION_SUCCEEDED")],
    }
    logs = {"taal-sense-0": [{"timestamp": "t1", "severity": "INFO", "textPayload": "run by ops@example.com\n"}],
            "taal-measure-0": [{"timestamp": "t2", "severity": "DEFAULT", "textPayload": measure_log or NO_PLAYS_IN_BIGQUERY}]}
    return FakeFetch(execs, logs)


def test_status_duration_and_streak():
    s = nr.summarize_execution(_ex("j", "e", "CONDITION_SUCCEEDED"), [])
    assert s["status"] == "green" and s["duration_s"] == 184.9 and s["execution"] == "e"
    assert nr.execution_status(_ex("j", "e", "CONDITION_FAILED")) == "red"
    assert nr.execution_status({"conditions": []}) == "running"
    assert nr.execution_status(_ex("j", "e", "CONDITION_SUCCEEDED", cancelledCount=1)) == "cancelled"
    exs = [{"status": st} for st in ("running", "green", "green", "red", "green")]
    assert nr.green_streak(exs) == 2
    assert nr.green_streak([{"status": "red"}, {"status": "green"}]) == 0


def test_build_report_first_run(tmp_path):
    fetch = _fakes()
    r = nr.build_report(fetch, fake_query(), "kutumb-mart", 3, "2026-09-29T03:00:00Z", None)
    assert r["label"] == "measured"
    assert r["jobs"]["taal-sense"]["green_streak"] == 3 and len(r["jobs"]["taal-sense"]["executions"]) == 3
    assert r["jobs"]["taal-sense"]["executions"][0]["log_tail"] == ["t1 INFO run by <redacted-email>"]
    assert r["measure_zero_plays_line_logged"] is True
    assert r["as_of"] == {"forecasts_as_of_values": ["2026-09-12"], "latest_forecasts_as_of": "2026-09-12", "sales_daily_max_date": "2026-09-12"}
    assert r["row_counts"]["gaps"] == 533 and r["row_counts"]["plays"] == 0
    assert r["row_count_stability"]["stable"] is None
    assert r["bigquery"]["bytes_billed"] == 150
    assert all(m in ("GET", "POST") for m, _, _ in fetch.calls)  # read-only: no :run, no DML


def test_growth_under_same_run_id_is_flagged(tmp_path):
    first = nr.build_report(_fakes(), fake_query(50120), "kutumb-mart", 3, "t", None)
    second = nr.build_report(_fakes(), fake_query(75180), "kutumb-mart", 3, "t", ("2026-09-28.json", first))
    stab = second["row_count_stability"]
    assert stab["stable"] is False and stab["compared_to"] == "2026-09-28.json"
    assert stab["changed"] == {"forecasts[sense_20260912_baseline_x]": {"previous": 50120, "current": 75180}}
    third = nr.build_report(_fakes(), fake_query(75180), "kutumb-mart", 3, "t", ("2026-09-29.json", second))
    assert third["row_count_stability"]["stable"] is True


def test_missing_zero_plays_line_is_reported():
    r = nr.build_report(_fakes(measure_log='{"plays": 2, "measured": 1}'), fake_query(), "kutumb-mart", 3, "t", None)
    assert r["measure_zero_plays_line_logged"] is False


def test_write_outputs_appends_readme_and_never_overwrites(tmp_path):
    r = nr.build_report(_fakes(sense_states=("CONDITION_FAILED", "CONDITION_SUCCEEDED")), fake_query(), "kutumb-mart", 3, "t", None)
    p1 = nr.write_outputs(r, tmp_path, "2026-09-29")
    p2 = nr.write_outputs(r, tmp_path, "2026-09-29")
    assert (p1.name, p2.name) == ("2026-09-29.json", "2026-09-29_2.json")
    assert json.loads(p1.read_text())["jobs"]["taal-sense"]["green_streak"] == 0
    readme = (tmp_path / "README.md").read_text()
    assert readme.startswith("# Nightly Sense/Measure run records") and readme.count("| [2026-09-29") == 2
    assert "| red 2026-09-28T20:00:05Z (240.0s) |" in readme
    assert nr.previous_report(tmp_path, "2026-09-29~")[0] == "2026-09-29_2.json"
    assert nr.previous_report(tmp_path, "2026-09-29") is None
