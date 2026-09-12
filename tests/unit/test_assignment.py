from hypothesis import given, settings
from hypothesis import strategies as st

from agents.gate.assignment import assign, assign_arm, bucket


def test_fraction_within_one_percent_on_10000_ids():
    ids = [f"CUST-{i:05d}" for i in range(10_000)]
    holdout = sum(1 for c in ids if assign_arm(c, "seed-play_chips_ds07_v1", 0.10) == "holdout")
    assert abs(holdout / 10_000 - 0.10) < 0.01


@settings(max_examples=50, deadline=None)
@given(seed=st.text(min_size=4, max_size=20), cid=st.text(min_size=1, max_size=20))
def test_arm_is_a_pure_function_of_seed_and_id(seed, cid):
    assert assign_arm(cid, seed, 0.2) == assign_arm(cid, seed, 0.2)
    assert 0 <= bucket(cid, seed) < 10_000


def test_assign_is_idempotent_and_dedupes():
    play = {"play_id": "play_x", "holdout": {"seed": "seed-x", "fraction": 0.1}}
    rows = assign(play, ["a", "b", "a"], assigned_at="2026-09-12T00:00:00Z")
    assert [r["customer_id"] for r in rows] == ["a", "b"]
    assert rows == assign(play, ["a", "b"], assigned_at="2026-09-12T00:00:00Z")


def test_different_seeds_give_different_arms_somewhere():
    ids = [f"C{i}" for i in range(500)]
    a = [assign_arm(c, "s1", 0.5) for c in ids]
    b = [assign_arm(c, "s2", 0.5) for c in ids]
    assert a != b
