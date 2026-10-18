"""Pure parts of harness/sealed_eval.py: the spend reservation under concurrency and the metric arithmetic."""
from harness import sealed_eval as se


class _Led:
    def __init__(self, spent):
        self.spent, self.stopped = spent, False


def test_reserver_refuses_a_run_that_could_pass_the_cap():
    led = _Led(9.0)
    r = se.Reserver(led, 10.0, 0.30)
    assert [r.try_start() for _ in range(4)] == [True, True, True, False]  # 9.0 + 3 x 0.30 fits, a 4th would reach 10.2
    r.release()
    assert r.try_start()
    led.stopped = True
    assert not r.try_start()


def test_reserver_without_a_ledger_never_blocks():
    assert se.Reserver(None, 10.0, 0.3).try_start()


def _run(rec, mech, status="proposed", first=True, it=1, viol=False):
    return {"verdict": "VALID", "status": status, "mechanic": mech, "recovery_inr": rec, "first_proposal_accepted": first, "iterations": it, "guardrail_violation_at_approve": viol, "elapsed_ms": 10000, "usd": 0.07}


def test_metrics():
    scs = [{"scenario_id": f"S0{i}", "stratum": s} for i, s in enumerate(["bundle", "do_nothing", "blanket_markdown"], 1)]
    ans = {
        "S01": {"best_classes_tied": ["bundle"], "best_recovery_inr": 1000.0, "blanket20_recovery_inr": 400.0},
        "S02": {"best_classes_tied": ["do_nothing"], "best_recovery_inr": 0.0, "blanket20_recovery_inr": -50.0},
        "S03": {"best_classes_tied": ["blanket_markdown"], "best_recovery_inr": 500.0, "blanket20_recovery_inr": 500.0},
    }
    runs = {"S01": _run(960.0, "bundle"), "S02": _run(0.0, None, "no_play", False, 3), "S03": _run(300.0, "outlet_markdown")}
    m = se.compute_metrics(scs, ans, runs)
    assert m["mechanic_match"] == {"n": 3, "of": 3}
    assert m["within_5pct"] == {"n": 1, "of": 3}
    assert m["beats_blanket20"]["n"] == 2 and m["beats_blanket20"]["of"] == 3
    assert m["restraint"]["do_nothing_stratum"] == {"correct": 1, "of": 1}
    assert m["restraint"]["blanket_markdown_stratum"] == {"correct": 1, "of": 1}
    assert m["recovery_captured"]["n"] == 2 and m["recovery_captured"]["min"] == 0.6
    assert m["regret_inr"]["sum"] == 240.0
    assert m["guardrail_violations_reaching_approve"] == 0
