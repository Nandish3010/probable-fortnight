"""Chat-as-demand-signal: customer_requests -> Sense gap detection (DECISIONS extension)."""
from datetime import date, timedelta

from agents.gate.config import load_tenant
from jobs.sense.forecast import forecast, run_id_for
from jobs.sense.gaps import detect


def _request(sku: str, node_id: str, customer_id: str, ts: str = "2026-09-12T10:00:00Z") -> dict:
    return {"tenant_id": "kutumb-mart", "customer_id": customer_id, "node_id": node_id, "sku": sku, "query_text": None, "request_type": "out_of_stock", "session_id": f"{customer_id}:web", "ts": ts}


def test_unmet_demand_gap_on_a_forecast_blind_spot(sandbox):
    """Inbound coverage makes stockout_risk stay quiet; two real customers hitting an empty shelf
    still raises a standalone unmet_demand gap the forecast alone would have missed."""
    tenant = load_tenant()
    as_of = date(2026, 9, 12)
    sku, node_id = "SKU-SALTED-CHIPS-100G", "DS-05"
    batches = [b for b in sandbox.read("inventory_batches") if not (b["sku"] == sku and b["node_id"] == node_id)]
    sandbox.write("inventory_batches", batches)
    inbound = sandbox.read("inbound")
    inbound.append({"tenant_id": "kutumb-mart", "po_id": "PO-TEST-COVER", "sku": sku, "node_id": node_id, "qty": 500, "eta": (as_of + timedelta(days=1)).isoformat()})
    sandbox.write("inbound", inbound)
    for cid in ("CUST-DEMO-1", "CUST-DEMO-2"):
        sandbox.append("customer_requests", [_request(sku, node_id, cid)])
    run_id = run_id_for(as_of, "test")
    fc = forecast(sandbox, as_of, run_id)
    gaps = detect(sandbox, fc, as_of, tenant, run_id)
    found = [g for g in gaps if g["sku"] == sku and g["node_id"] == node_id]
    assert not any(g["type"] == "stockout_risk" for g in found), "inbound coverage should keep stockout_risk quiet"
    unmet = next((g for g in found if g["type"] == "unmet_demand"), None)
    assert unmet, "two real customer requests on an empty, uncovered-by-forecast shelf must raise unmet_demand"
    assert unmet["units_at_risk"] == 2 and unmet["evidence"]["distinct_customers"] == 2 and unmet["evidence"]["requests_count"] == 2
    assert unmet["deadline_type"] == "lead_time" and unmet["evidence"]["on_hand"] == 0


def test_below_threshold_or_restocked_raises_nothing(sandbox):
    tenant = load_tenant()
    as_of = date(2026, 9, 12)
    sku, node_id = "SKU-SALTED-CHIPS-500G", "DS-05"
    batches = [b for b in sandbox.read("inventory_batches") if not (b["sku"] == sku and b["node_id"] == node_id)]
    sandbox.write("inventory_batches", batches)
    sandbox.append("customer_requests", [_request(sku, node_id, "CUST-DEMO-1")])  # only one distinct customer
    run_id = run_id_for(as_of, "test2")
    fc = forecast(sandbox, as_of, run_id)
    gaps = detect(sandbox, fc, as_of, tenant, run_id)
    assert not any(g["sku"] == sku and g["node_id"] == node_id and g["type"] == "unmet_demand" for g in gaps)

    sku2, node_id2 = "SKU-BANANA-CHIPS-100G", "DS-06"
    batches2 = sandbox.read("inventory_batches")
    batches2.append({"tenant_id": "kutumb-mart", "batch_id": "B-RESTOCK-TEST", "sku": sku2, "node_id": node_id2, "qty_on_hand": 40, "expiry_date": "2027-01-01", "online_sellby_date": "2026-11-01", "received_at": "2026-09-10", "source": "system", "capture_ref": None, "sellby_rule_version": tenant.sellby_rule.version})
    sandbox.write("inventory_batches", batches2)
    for cid in ("CUST-DEMO-3", "CUST-DEMO-4"):
        sandbox.append("customer_requests", [_request(sku2, node_id2, cid)])
    fc2 = forecast(sandbox, as_of, run_id_for(as_of, "test3"))
    gaps2 = detect(sandbox, fc2, as_of, tenant, run_id_for(as_of, "test3"))
    assert not any(g["sku"] == sku2 and g["node_id"] == node_id2 and g["type"] == "unmet_demand" for g in gaps2), "restocked since the requests: no longer a gap"


def test_stockout_risk_evidence_enriched_with_real_requests(sandbox):
    """When customer_requests land on a pair that already has a forecast-driven stockout_risk gap,
    they corroborate it (evidence.requests_count/distinct_customers) rather than duplicating it."""
    tenant = load_tenant()
    as_of = date(2026, 9, 12)
    for cid in ("CUST-DEMO-5", "CUST-DEMO-6", "CUST-DEMO-7"):
        sandbox.append("customer_requests", [_request("SKU-COLA-ZERO-500ML", "DS-07", cid)])
    run_id = run_id_for(as_of, "test4")
    fc = forecast(sandbox, as_of, run_id)
    gaps = detect(sandbox, fc, as_of, tenant, run_id)
    cola = next(g for g in gaps if g["gap_id"] == "gap_cola_ds07")
    assert cola["type"] == "stockout_risk"
    assert cola["evidence"]["distinct_customers"] == 3 and cola["evidence"]["requests_count"] == 3
    assert not any(g["sku"] == "SKU-COLA-ZERO-500ML" and g["node_id"] == "DS-07" and g["type"] == "unmet_demand" for g in gaps), "already covered by stockout_risk; no duplicate gap"
