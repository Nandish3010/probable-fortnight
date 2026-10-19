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


def _run(rec, mech, outcome="model_play", first=True, it=1, viol=False):
    return {"verdict": "VALID", "outcome": outcome, "status": "proposed" if outcome == "model_play" else "no_play", "mechanic": mech, "recovery_inr": rec, "first_proposal_accepted": first, "iterations": it, "guardrail_violation_at_approve": viol, "elapsed_ms": 10000, "usd": 0.07}


def test_metrics():
    scs = [{"scenario_id": f"S0{i}", "gap": {"type": "expiry_writeoff"}} for i in (1, 2, 3, 4)]
    ans = {k: {"oracle_upper_bound_inr": ub, "blanket20_recovery_inr": bl} for k, ub, bl in (("S01", 1000.0, 400.0), ("S02", 800.0, 500.0), ("S03", 500.0, 100.0), ("S04", 500.0, 100.0))}
    runs = {"S01": _run(960.0, "bundle"), "S02": _run(300.0, "coupon"), "S03": _run(450.0, "outlet_markdown", "deterministic_fallback"), "S04": _run(0.0, None, "no_play", False, 3)}
    m = se.compute_metrics(scs, ans, runs)
    assert m["beats_blanket20"]["n"] == 1 and m["beats_blanket20"]["of"] == 4  # S03's fallback play and S04's no play never beat a baseline
    assert m["beats_blanket20"]["total_beat_inr_where_beaten"] == 560.0
    assert m["beats_do_nothing"]["n"] == 2
    assert m["outcomes"] == {"model_play": 2, "deterministic_fallback": 1, "no_play": 1}
    assert m["mechanic_mix"] == {"bundle": 1, "coupon": 1}
    assert m["estimator_upper_bound_secondary"]["captured_min"] == 0.0
    assert m["guardrail_violations_reaching_approve"] == 0
