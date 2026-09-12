import asyncio

from mcp.client import Client

from agents.mcp_orders.server import server


def test_place_order_over_mcp_writes_play_id(sandbox):
    async def go():
        async with Client(server) as c:
            tools = await c.list_tools()
            assert "place_order" in [t.name for t in tools.tools]
            r = await c.call_tool("place_order", {"customer_id": "CUST-MEENA", "node_id": "DS-07", "lines": [{"sku": "SKU-MASALA-CHIPS-200G", "qty": 2, "price": 30.0, "discount": 3.0}], "play_id": "play_chips_ds07_v1", "data_dir": str(sandbox.root), "base_dir": str(sandbox.base.root), "ts": "2026-09-12T09:00:00Z"})
            return r.structured_content

    out = asyncio.run(go())
    assert out["order_id"].startswith("ORD-") and out["total_inr"] == 54.0
    lines = [ln for ln in sandbox.read("order_lines") if ln["order_id"] == out["order_id"]]
    assert lines and lines[0]["play_id"] == "play_chips_ds07_v1"
    assert not any(ln["order_id"] == out["order_id"] for ln in sandbox.base.read("order_lines")), "base tenant untouched"
