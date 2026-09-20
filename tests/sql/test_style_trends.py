from datetime import date

from agents.gate.config import load_tenant
from jobs.sense.trends import build_style_trends


def _request(customer_id: str, node_id: str = "DS-07", garment_type: str = "kurta", colour_family: str = "yellow-orange", occasion: str | None = "casual", fulfilled: bool = True, ts: str = "2026-09-10T10:00:00Z") -> dict:
    return {
        "tenant_id": "kutumb-mart", "customer_id": customer_id, "node_id": node_id,
        "session_id": f"{customer_id}:web", "ts": ts, "source": "suggest_pairings",
        "garment_type": garment_type, "colour": "mustard", "colour_family": colour_family,
        "occasion": occasion, "query_text": None, "matched_sku": "APP-KURTA-MUSTARD-W" if fulfilled else None,
        "fulfilled": fulfilled,
    }


def test_trend_raised_from_three_asks_two_customers_one_unfulfilled(sandbox):
    tenant = load_tenant()
    sandbox.write("style_requests", [
        _request("CUST-A"), _request("CUST-A", fulfilled=False), _request("CUST-B"),
    ])
    rows = build_style_trends(sandbox, date(2026, 9, 12), tenant, "trends-test")
    assert len(rows) == 1
    row = rows[0]
    assert row["node_id"] == "DS-07" and row["garment_type"] == "kurta" and row["colour_family"] == "yellow-orange"
    assert row["asks"] == 3 and row["distinct_customers"] == 2 and row["unfulfilled_asks"] == 1
    assert row["window_days"] == int(tenant.thresholds["style_trends_lookback_days"])


def test_single_ask_below_threshold_raises_nothing(sandbox):
    tenant = load_tenant()
    sandbox.write("style_requests", [_request("CUST-A")])
    rows = build_style_trends(sandbox, date(2026, 9, 12), tenant, "trends-test")
    assert rows == []


def test_ask_before_lookback_window_is_ignored(sandbox):
    tenant = load_tenant()
    sandbox.write("style_requests", [
        _request("CUST-A", ts="2026-01-01T10:00:00Z"), _request("CUST-B", ts="2026-01-02T10:00:00Z"),
    ])
    rows = build_style_trends(sandbox, date(2026, 9, 12), tenant, "trends-test")
    assert rows == []


def test_distinct_groups_by_node_garment_colour_occasion(sandbox):
    tenant = load_tenant()
    sandbox.write("style_requests", [
        _request("CUST-A", node_id="DS-07"), _request("CUST-B", node_id="DS-07"),
        _request("CUST-A", node_id="DS-04"), _request("CUST-B", node_id="DS-04"),
    ])
    rows = build_style_trends(sandbox, date(2026, 9, 12), tenant, "trends-test")
    assert {r["node_id"] for r in rows} == {"DS-07", "DS-04"}
    assert all(r["asks"] == 2 for r in rows)


def test_ddl_and_jsonl_agree_on_the_new_tables(sandbox):
    from data.bigquery.local import build

    sandbox.write("style_requests", [_request("CUST-A"), _request("CUST-B")])
    con = build(sandbox)
    assert con.execute("SELECT COUNT(*) FROM apparel_products").fetchone()[0] > 0
    assert con.execute("SELECT COUNT(*) FROM apparel_stock").fetchone()[0] > 0
    assert con.execute("SELECT COUNT(*) FROM style_requests").fetchone()[0] == 2
    assert con.execute("SELECT COUNT(*) FROM customer_style_profile").fetchone()[0] == 0
